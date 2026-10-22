"""Platform admins (PLAN.md §7 /admin): the super admin adds the others and
ticks what each may do (app/core/admin_permissions.py).

The super admin is made from a shell on the server
(scripts.create_platform_admin) and can't be changed from here, so nobody
signed in to /admin can take it over or lock it out. Every change is in the
activity log, under no gym.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core import admin_permissions
from app.core.admin_permissions import GRANTABLE, AdminPermission
from app.core.errors import AppError, not_found
from app.core.security import hash_password
from app.db.session import get_db
from app.models.staff import StaffUser
from app.schemas.platform import (
    AdminPasswordIn,
    PlatformAdminCreate,
    PlatformAdminRead,
    PlatformAdminUpdate,
)
from app.services import activity, sessions, two_step

router = APIRouter(prefix="/admin/admins", tags=["platform admin"])

SUPER = Depends(require_admin(AdminPermission.ADMINS))

LOGIN_TAKEN = AppError(
    409, "account_exists", "An account with that email or phone already exists."
)


def _read(admin: StaffUser) -> PlatformAdminRead:
    return PlatformAdminRead(
        id=admin.id,
        name=admin.name,
        email=admin.email,
        phone=admin.phone,
        is_super_admin=admin.is_super_admin,
        permissions=sorted(admin_permissions.effective(admin)),
        is_active=admin.is_active,
        two_step_enabled=admin.two_step_enabled,
        last_login_at=admin.last_login_at,
    )


def _grantable(keys: list[str]) -> list[str]:
    unknown = set(keys) - GRANTABLE
    if unknown:
        raise AppError(
            422,
            "bad_permission",
            "That can't be given: only the super admin adds admins.",
            permissions=", ".join(sorted(unknown)),
        )
    return sorted(set(keys))


def _login_taken(
    db: Session, email: str | None, phone: str | None, exclude: uuid.UUID | None = None
) -> bool:
    for column, value in ((StaffUser.email, email), (StaffUser.phone, phone)):
        if (
            value
            and db.scalars(
                select(StaffUser.id).where(column == value, StaffUser.id != exclude)
            ).first()
        ):
            return True
    return False


def _sub_admin(db: Session, admin_id: uuid.UUID) -> StaffUser:
    """Another admin the super admin may change: never a super admin."""
    admin = db.get(StaffUser, admin_id)
    if admin is None or not admin.is_platform_admin:
        raise not_found("No such admin.")
    if admin.is_super_admin:
        raise AppError(
            403,
            "super_admin_protected",
            "The super admin is changed only from the server.",
        )
    return admin


@router.get("", response_model=list[PlatformAdminRead])
def list_admins(
    db: Session = Depends(get_db), me: StaffUser = SUPER
) -> list[PlatformAdminRead]:
    rows = db.scalars(
        select(StaffUser)
        .where(StaffUser.is_platform_admin)
        .order_by(StaffUser.is_super_admin.desc(), StaffUser.name)
    ).all()
    return [_read(admin) for admin in rows]


@router.post("", response_model=PlatformAdminRead, status_code=status.HTTP_201_CREATED)
def create_admin(
    payload: PlatformAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    me: StaffUser = SUPER,
) -> PlatformAdminRead:
    """Two-step sign-in is set up at their first sign-in, as for every admin."""
    permissions = _grantable(payload.permissions)
    if _login_taken(db, payload.email, payload.phone):
        raise LOGIN_TAKEN
    admin = StaffUser(
        gym_id=None,
        is_platform_admin=True,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        permissions=permissions,
    )
    db.add(admin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise LOGIN_TAKEN from exc
    activity.staff_action(
        db,
        me,
        "admin.created",
        entity="staff",
        entity_id=admin.id,
        changes={
            "name": admin.name,
            "email": admin.email,
            "phone": admin.phone,
            "permissions": permissions,
        },
        request=request,
    )
    db.commit()
    return _read(admin)


@router.patch("/{admin_id}", response_model=PlatformAdminRead)
def update_admin(
    admin_id: uuid.UUID,
    payload: PlatformAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    me: StaffUser = SUPER,
) -> PlatformAdminRead:
    """What they may do, their name and login, or turning them off, which
    signs them out everywhere."""
    admin = _sub_admin(db, admin_id)
    changes = payload.model_dump(exclude_unset=True)
    fields = ("name", "email", "phone", "permissions", "is_active")
    before = {name: getattr(admin, name) for name in fields}

    email = changes.get("email", admin.email)
    phone = changes.get("phone", admin.phone)
    if not email and not phone:
        raise AppError(
            422, "needs_login", "Keep a phone number or an email to sign in with."
        )
    if _login_taken(db, email, phone, exclude=admin.id):
        raise LOGIN_TAKEN

    if changes.get("permissions") is not None:
        admin.permissions = _grantable(changes["permissions"])
    for name in ("name", "email", "phone", "is_active"):
        if name in changes and (
            changes[name] is not None or name in ("email", "phone")
        ):
            setattr(admin, name, changes[name])
    if changes.get("is_active") is False:
        sessions.revoke_all(db, admin)

    diff = activity.diff(before, {name: getattr(admin, name) for name in fields})
    if diff:
        activity.staff_action(
            db,
            me,
            "admin.updated",
            entity="staff",
            entity_id=admin.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return _read(admin)


@router.post("/{admin_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    admin_id: uuid.UUID,
    payload: AdminPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
    me: StaffUser = SUPER,
) -> None:
    """A new password for an admin who forgot theirs. Signs them out everywhere."""
    admin = _sub_admin(db, admin_id)
    admin.password_hash = hash_password(payload.new_password)
    sessions.revoke_all(db, admin)
    activity.staff_action(
        db,
        me,
        "admin.password_reset",
        entity="staff",
        entity_id=admin.id,
        request=request,
    )
    db.commit()


@router.post("/{admin_id}/two-step/reset", response_model=PlatformAdminRead)
def reset_two_step(
    admin_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    me: StaffUser = SUPER,
) -> PlatformAdminRead:
    """An admin lost their phone: two-step sign-in off, set up again at their
    next sign-in."""
    admin = _sub_admin(db, admin_id)
    two_step.disable(db, admin)
    activity.staff_action(
        db,
        me,
        "admin.two_step_reset",
        entity="staff",
        entity_id=admin.id,
        request=request,
    )
    db.commit()
    return _read(admin)
