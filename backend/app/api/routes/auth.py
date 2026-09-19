"""Gym sign-up and staff sign-in (PLAN.md §8, Auth).

The access token goes back in the response body and lives only in the page's
memory. The refresh token is an httpOnly cookie scoped to /api/v1/auth, so page
scripts never see it and it is only ever sent to these routes.
"""

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_staff
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import effective_permissions
from app.core.phone import normalize_phone
from app.core.security import burn_password_check, hash_password, verify_password
from app.core.time import today_in_nepal
from app.db.session import get_db
from app.models.billing import GymSubscription
from app.models.gym import Gym
from app.models.staff import StaffBranchAccess, StaffUser
from app.schemas.auth import (
    GymRead,
    GymSignup,
    LoginRequest,
    Me,
    SessionResponse,
    StaffRead,
    SubscriptionRead,
)
from app.schemas.staff import PasswordChange
from app.services import activity, registration, sessions, storage

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "gb_refresh"
REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"

BAD_LOGIN = AppError(401, "bad_login", "Incorrect email, phone or password.")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _gym_read(gym: Gym) -> GymRead:
    read = GymRead.model_validate(gym)
    read.logo_url = storage.signed_url(gym.logo_key)
    return read


def build_me(db: Session, staff: StaffUser) -> Me:
    gym = db.get(Gym, staff.gym_id) if staff.gym_id else None
    subscription = None
    branch_ids = None
    if gym is not None:
        latest = db.scalars(
            select(GymSubscription)
            .where(GymSubscription.gym_id == gym.id)
            .order_by(GymSubscription.ends_on.desc())
        ).first()
        if latest is not None:
            days_left = (latest.ends_on - today_in_nepal()).days + 1
            subscription = SubscriptionRead(
                status=latest.status,
                starts_on=latest.starts_on,
                ends_on=latest.ends_on,
                days_left=max(days_left, 0),
            )
        if not staff.is_owner:
            rows = db.scalars(
                select(StaffBranchAccess.branch_id).where(
                    StaffBranchAccess.staff_user_id == staff.id
                )
            ).all()
            branch_ids = sorted(rows) or None

    permissions = (
        sorted(effective_permissions(is_owner=staff.is_owner, stored=staff.permissions))
        if gym is not None
        else []
    )
    return Me(
        staff=StaffRead.model_validate(staff),
        gym=_gym_read(gym) if gym else None,
        permissions=permissions,
        branch_ids=branch_ids,
        subscription=subscription,
    )


def _session_response(
    db: Session, issued: sessions.Issued, response: Response
) -> SessionResponse:
    if issued.refresh_token is not None:
        _set_refresh_cookie(response, issued.refresh_token)
    return SessionResponse(
        access_token=issued.access_token,
        expires_in=settings.access_token_minutes * 60,
        me=build_me(db, issued.staff),
    )


@router.post(
    "/register-gym",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_gym(
    payload: GymSignup,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Gym + owner + first branch + calendar choice, and a free trial."""
    registered = registration.register_gym(db, payload, request)
    issued = sessions.start(db, registered.owner, request)
    db.commit()
    return _session_response(db, issued, response)


def _find_staff(db: Session, identifier: str) -> StaffUser | None:
    identifier = identifier.strip()
    if "@" in identifier:
        condition = StaffUser.email == identifier.lower()
    else:
        try:
            condition = StaffUser.phone == normalize_phone(identifier)
        except ValueError:
            return None
    return db.scalars(select(StaffUser).where(condition)).first()


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Staff sign in with their email or phone and a password."""
    staff = _find_staff(db, payload.identifier)
    if staff is None:
        burn_password_check()
        raise BAD_LOGIN
    # One message for an unknown account and a wrong password, so the answer
    # never confirms who has an account.
    if not verify_password(payload.password, staff.password_hash):
        raise BAD_LOGIN
    if not staff.is_active:
        raise AppError(403, "account_disabled", "This account has been disabled.")

    issued = sessions.start(db, staff, request)
    activity.staff_action(
        db,
        staff,
        "staff.signed_in",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    db.commit()
    return _session_response(db, issued, response)


@router.post("/refresh", response_model=SessionResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    gb_refresh: str | None = Cookie(default=None),
) -> SessionResponse | JSONResponse:
    """A new access token for the browser holding a live refresh cookie."""
    issued = sessions.refresh(db, gb_refresh)
    if issued is None:
        db.rollback()
        # Built by hand rather than raised, so the dead cookie is cleared too.
        ended = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "You have been signed out.", "code": "session_ended"},
        )
        _clear_refresh_cookie(ended)
        return ended
    db.commit()
    return _session_response(db, issued, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    gb_refresh: str | None = Cookie(default=None),
) -> Response:
    session = sessions.revoke(db, gb_refresh)
    if session is not None:
        staff = db.get(StaffUser, session.staff_user_id)
        if staff is not None:
            activity.staff_action(
                db,
                staff,
                "staff.signed_out",
                entity="staff",
                entity_id=staff.id,
                request=request,
            )
    db.commit()
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(done)
    return done


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    gb_refresh: str | None = Cookie(default=None),
) -> Response:
    """Change your own password. Other devices are signed out; this one stays."""
    if not verify_password(payload.current_password, staff.password_hash):
        raise AppError(403, "wrong_password", "That is not your current password.")
    staff.password_hash = hash_password(payload.new_password)
    current = sessions.find(db, gb_refresh)
    sessions.revoke_all(db, staff, keep=current.id if current else None)
    activity.staff_action(
        db,
        staff,
        "staff.password_changed",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=Me)
def me(staff: StaffUser = Depends(current_staff), db: Session = Depends(get_db)) -> Me:
    return build_me(db, staff)
