"""Request dependencies: who is calling, and what they may do.

Every gym route declares what it needs with `require(...)`:

    @router.patch("/gym")
    def update_gym(ctx: StaffContext = Depends(require(Permission.SETUP_GYM))):

`require()` with no permission means "any signed-in staff of the gym" and is
allowed only on the routes listed in tests/regression/test_route_permissions.py.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError, unauthorized
from app.core.permissions import Permission, effective_permissions
from app.core.security import (
    TokenError,
    decode_access_token,
    decode_member_token,
    hash_refresh_token,
)
from app.core.time import utcnow
from app.db.session import get_db
from app.models.member import Member
from app.models.member_app import Device, MemberSession
from app.models.staff import StaffBranchAccess, StaffSession, StaffUser
from app.services import subscription

# auto_error=False so a missing header gets our 401, not FastAPI's 403.
bearer = HTTPBearer(auto_error=False)


def current_staff(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Session = Depends(get_db),
) -> StaffUser:
    """The signed-in account, re-checked against the database every time.

    A disabled account, a revoked session or an account moved between gyms
    stops working on its very next request, not when the token expires.
    """
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise unauthorized(exc.code, str(exc)) from exc

    session = db.get(StaffSession, claims.session_id)
    if (
        session is None
        or session.staff_user_id != claims.staff_id
        or session.revoked_at is not None
        or session.expires_at <= utcnow()
    ):
        raise unauthorized("session_ended", "You have been signed out.")

    staff = db.get(StaffUser, claims.staff_id)
    if staff is None or not staff.is_active or staff.gym_id != claims.gym_id:
        raise unauthorized("session_ended", "You have been signed out.")
    return staff


def staff_context(
    staff: StaffUser = Depends(current_staff), db: Session = Depends(get_db)
) -> StaffContext:
    if staff.gym_id is None:
        # A platform admin has no gym of their own; /admin routes serve them.
        raise AppError(403, "no_gym", "This account does not belong to a gym.")

    branch_ids = frozenset(
        db.scalars(
            select(StaffBranchAccess.branch_id).where(
                StaffBranchAccess.staff_user_id == staff.id
            )
        )
    )
    return StaffContext(
        staff=staff,
        gym_id=staff.gym_id,
        permissions=effective_permissions(
            is_owner=staff.is_owner, stored=staff.permissions
        ),
        # The owner works in every branch, whatever rows exist.
        branch_ids=None if staff.is_owner or not branch_ids else branch_ids,
    )


READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def require(
    *permissions: Permission, allow_when_lapsed: bool = False
) -> Callable[..., StaffContext]:
    """A dependency that admits staff holding every one of `permissions`.

    Changes are also refused once the gym's subscription has lapsed past its
    grace days (PLAN.md §5.7): the dashboard is then read-only. Paying us is
    the exception, marked with `allow_when_lapsed`.
    """

    def dependency(
        request: Request,
        ctx: StaffContext = Depends(staff_context),
        db: Session = Depends(get_db),
    ) -> StaffContext:
        if (
            request.method not in READ_METHODS
            and not allow_when_lapsed
            and subscription.is_read_only(db, ctx.gym_id)
        ):
            raise AppError(
                402,
                "subscription_lapsed",
                "Your GymBahi subscription has lapsed. You can still see and export "
                "everything; pay to make changes again.",
            )
        for permission in permissions:
            if not ctx.can(permission):
                raise AppError(
                    403,
                    "permission_denied",
                    "You don't have permission to do this.",
                    permission=permission.value,
                )
        return ctx

    # Read by the route-permission regression test.
    dependency.required_permissions = frozenset(permissions)  # type: ignore[attr-defined]
    dependency.__name__ = "require_" + (
        "_".join(p.value for p in permissions) or "signed_in"
    )
    return dependency


def current_member(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Session = Depends(get_db),
) -> Member:
    """The member signed in to the member app. Members only ever see their own
    records (PLAN.md §11); every /m/ route takes the member from here."""
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_member_token(credentials.credentials)
    except TokenError as exc:
        raise unauthorized(exc.code, str(exc)) from exc
    session = db.get(MemberSession, claims.session_id)
    if (
        session is None
        or session.member_id != claims.member_id
        or session.revoked_at is not None
        or session.expires_at <= utcnow()
    ):
        raise unauthorized("session_ended", "You have been signed out.")
    member = db.get(Member, claims.member_id)
    if member is None or not member.app_access or member.gym_id != claims.gym_id:
        raise unauthorized("session_ended", "You have been signed out.")
    return member


DEVICE_HEADER = "X-Device-Token"


def current_device(
    x_device_token: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Device:
    """A registered door scanner. It can check people in and nothing else."""
    if not x_device_token:
        raise unauthorized("no_device", "This device is not registered.")
    device = db.scalars(
        select(Device).where(Device.token_hash == hash_refresh_token(x_device_token))
    ).first()
    if device is None or device.revoked_at is not None:
        raise unauthorized("device_revoked", "This device is no longer registered.")
    device.last_seen_at = utcnow()
    return device


def require_platform_admin(
    staff: StaffUser = Depends(current_staff),
) -> StaffUser:
    if not staff.is_platform_admin:
        raise AppError(403, "platform_admin_only", "Platform administrators only.")
    return staff
