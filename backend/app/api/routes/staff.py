"""Staff accounts and their permissions (PLAN.md §2.1).

The rules the system enforces:

* The owner has every permission; nobody can remove or edit the owner's
  permissions, branches or access. The owner may edit their own name and login.
* Staff with Manage staff can only give permissions they hold, never Manage
  staff itself, and only branches they work in. They cannot edit an account
  that itself has Manage staff: only the owner manages managers.
* Nobody can disable their own account.
* Disabling an account, or changing its password, signs it out everywhere.
* Every change is in the activity log.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.errors import AppError
from app.core.permissions import (
    ALL_PERMISSIONS,
    OWNER_ONLY_GRANT,
    PRESETS,
    Permission,
    parse_permissions,
    ungrantable,
)
from app.core.security import hash_password
from app.db.session import get_db
from app.models.gym import Branch
from app.models.staff import StaffBranchAccess, StaffUser
from app.schemas.staff import (
    PasswordSet,
    PermissionCatalog,
    PermissionInfo,
    StaffCreate,
    StaffMember,
    StaffUpdate,
)
from app.services import activity, sessions

router = APIRouter(prefix="/staff", tags=["staff"])

MANAGE = require(Permission.STAFF_MANAGE)
LOGIN_TAKEN = AppError(
    409, "account_exists", "An account with that email or phone already exists."
)


def _branch_ids(db: Session, staff_id: uuid.UUID) -> list[uuid.UUID]:
    return sorted(
        db.scalars(
            select(StaffBranchAccess.branch_id).where(
                StaffBranchAccess.staff_user_id == staff_id
            )
        )
    )


def _read(db: Session, staff: StaffUser) -> StaffMember:
    read = StaffMember.model_validate(staff)
    read.permissions = (
        sorted(staff.permissions)
        if not staff.is_owner
        else sorted(p.value for p in ALL_PERMISSIONS)
    )
    read.branch_ids = [] if staff.is_owner else _branch_ids(db, staff.id)
    return read


def _check_grant(
    ctx: StaffContext, requested: list[str], current: list[str]
) -> list[str]:
    """The permission list to store, or AppError if the caller may not set it."""
    requested_set, current_set = set(requested), set(current)
    refused = ungrantable(
        ctx.permissions,
        granter_is_owner=ctx.staff.is_owner,
        requested=requested_set - current_set,
    )
    if not ctx.staff.is_owner:
        # Removing a permission you don't hold is also handing out a decision
        # that isn't yours.
        refused += sorted(
            key
            for key in current_set - requested_set
            if key not in {p.value for p in ctx.permissions}
            or key in {p.value for p in OWNER_ONLY_GRANT}
        )
    if refused:
        raise AppError(
            403,
            "cannot_grant",
            "You can only give permissions you have yourself.",
            permissions=sorted(set(refused)),
        )
    return sorted(p.value for p in parse_permissions(requested_set))


def _check_branches(
    db: Session, ctx: StaffContext, branch_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    wanted = set(branch_ids)
    if wanted:
        found = set(
            db.scalars(
                select(Branch.id).where(
                    Branch.gym_id == ctx.gym_id, Branch.id.in_(wanted)
                )
            )
        )
        if found != wanted:
            raise AppError(422, "bad_branch", "That branch does not exist.")
    if ctx.branch_ids is not None:
        # Limited to some branches yourself: you can't give "every branch",
        # nor a branch you don't work in.
        if not wanted or not wanted <= ctx.branch_ids:
            raise AppError(
                403, "cannot_grant", "You can only give access to your own branches."
            )
    return sorted(wanted)


def _set_branches(db: Session, staff: StaffUser, branch_ids: list[uuid.UUID]) -> None:
    db.execute(
        delete(StaffBranchAccess).where(StaffBranchAccess.staff_user_id == staff.id)
    )
    for branch_id in branch_ids:
        db.add(StaffBranchAccess(staff_user_id=staff.id, branch_id=branch_id))


def _login_taken(
    db: Session, email: str | None, phone: str | None, exclude: uuid.UUID | None = None
) -> bool:
    for column, value in ((StaffUser.email, email), (StaffUser.phone, phone)):
        if value:
            stmt = select(StaffUser.id).where(column == value)
            if exclude:
                stmt = stmt.where(StaffUser.id != exclude)
            if db.scalar(stmt):
                return True
    return False


def _target(db: Session, ctx: StaffContext, staff_id: uuid.UUID) -> StaffUser:
    staff = get_in_gym(db, StaffUser, staff_id, ctx, message="No such staff member.")
    if not ctx.staff.is_owner:
        if staff.is_owner:
            raise AppError(
                403, "owner_protected", "Only the owner can change the owner."
            )
        if Permission.STAFF_MANAGE.value in staff.permissions:
            raise AppError(
                403, "manager_protected", "Only the owner can change this account."
            )
    return staff


@router.get("/permissions", response_model=PermissionCatalog)
def permission_catalog(ctx: StaffContext = Depends(MANAGE)) -> PermissionCatalog:
    """The checklist on the staff form, with its starting points."""
    grantable = sorted(
        p.value
        for p in Permission
        if ctx.staff.is_owner or (p in ctx.permissions and p not in OWNER_ONLY_GRANT)
    )
    return PermissionCatalog(
        permissions=[
            PermissionInfo(key=p.value, area=p.value.split(".")[0]) for p in Permission
        ],
        presets={name: sorted(p.value for p in keys) for name, keys in PRESETS.items()},
        grantable=grantable,
    )


@router.get("", response_model=list[StaffMember])
def list_staff(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(MANAGE)
) -> list[StaffMember]:
    rows = db.scalars(
        for_gym(select(StaffUser), StaffUser, ctx).order_by(
            StaffUser.is_owner.desc(), StaffUser.name
        )
    )
    return [_read(db, s) for s in rows]


@router.post("", response_model=StaffMember, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> StaffMember:
    permissions = _check_grant(ctx, payload.permissions, [])
    branch_ids = _check_branches(db, ctx, payload.branch_ids)
    if _login_taken(db, payload.email, payload.phone):
        raise LOGIN_TAKEN

    staff = StaffUser(
        gym_id=ctx.gym_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        permissions=permissions,
    )
    db.add(staff)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise LOGIN_TAKEN from exc
    _set_branches(db, staff, branch_ids)
    activity.staff_action(
        db,
        ctx.staff,
        "staff.created",
        entity="staff",
        entity_id=staff.id,
        changes={
            "name": staff.name,
            "email": staff.email,
            "phone": staff.phone,
            "permissions": permissions,
            "branch_ids": branch_ids,
        },
        request=request,
    )
    db.commit()
    return _read(db, staff)


@router.patch("/{staff_id}", response_model=StaffMember)
def update_staff(
    staff_id: uuid.UUID,
    payload: StaffUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> StaffMember:
    staff = _target(db, ctx, staff_id)
    changes = payload.model_dump(exclude_unset=True)
    before = {
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        "permissions": sorted(staff.permissions),
        "branch_ids": _branch_ids(db, staff.id),
        "is_active": staff.is_active,
    }

    if staff.is_owner and {"permissions", "branch_ids", "is_active"} & set(changes):
        raise AppError(
            403, "owner_protected", "The owner always has every permission and branch."
        )
    if changes.get("is_active") is False and staff.id == ctx.staff.id:
        raise AppError(
            409, "cannot_disable_self", "You can't disable your own account."
        )

    email = changes.get("email", staff.email)
    phone = changes.get("phone", staff.phone)
    if not email and not phone:
        raise AppError(
            422, "needs_login", "Keep a phone number or an email to sign in with."
        )
    if _login_taken(db, email, phone, exclude=staff.id):
        raise LOGIN_TAKEN

    if "permissions" in changes:
        staff.permissions = _check_grant(ctx, changes["permissions"], staff.permissions)
    if "branch_ids" in changes:
        _set_branches(db, staff, _check_branches(db, ctx, changes["branch_ids"]))
    for name in ("name", "email", "phone", "is_active"):
        if name in changes and (
            changes[name] is not None or name in ("email", "phone")
        ):
            setattr(staff, name, changes[name])
    if changes.get("is_active") is False:
        sessions.revoke_all(db, staff)

    db.flush()
    after = {
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        "permissions": sorted(staff.permissions),
        "branch_ids": _branch_ids(db, staff.id),
        "is_active": staff.is_active,
    }
    diff = activity.diff(before, after)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "staff.updated",
            entity="staff",
            entity_id=staff.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return _read(db, staff)


@router.post("/{staff_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    staff_id: uuid.UUID,
    payload: PasswordSet,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> None:
    """Reset a colleague's password. Signs them out everywhere."""
    staff = _target(db, ctx, staff_id)
    if staff.id == ctx.staff.id:
        raise AppError(
            409,
            "use_own_password_change",
            "Change your own password from your profile.",
        )
    staff.password_hash = hash_password(payload.new_password)
    sessions.revoke_all(db, staff)
    activity.staff_action(
        db,
        ctx.staff,
        "staff.password_reset",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    db.commit()
