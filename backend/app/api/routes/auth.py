"""Gym sign-up and staff sign-in (PLAN.md §8, Auth).

The access token goes back in the response body and lives only in the page's
memory. The refresh token is an httpOnly cookie scoped to /api/v1/auth, so page
scripts never see it and it is only ever sent to these routes.
"""

import uuid
from typing import NoReturn

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_session, current_staff
from app.api.presenters import gym_read
from app.core import admin_permissions
from app.core.config import settings
from app.core.errors import AppError, not_found
from app.core.permissions import effective_permissions
from app.core.security import (
    TWO_STEP_MINUTES,
    TokenError,
    burn_password_check,
    create_two_step_token,
    decode_two_step_token,
    hash_password,
    verify_password,
)
from app.core.time import utcnow
from app.db.session import get_db
from app.models.activity import ACTOR_SYSTEM
from app.models.gym import GYM_ACTIVE, Gym
from app.models.staff import StaffBranchAccess, StaffSession, StaffUser
from app.schemas.auth import (
    DeviceSession,
    GymSignup,
    LanguageIn,
    LoginRequest,
    Me,
    PasswordConfirm,
    PasswordResetConfirm,
    PasswordResetRequest,
    RecoveryCodes,
    SessionResponse,
    SignedOut,
    StaffRead,
    SubscriptionRead,
    TwoStepChallenge,
    TwoStepEnable,
    TwoStepLogin,
    TwoStepSetupRead,
    TwoStepStatus,
)
from app.schemas.staff import PasswordChange
from app.services import (
    activity,
    changelog,
    live,
    registration,
    sessions,
    staff_auth,
    subscription,
    two_step,
)
from app.services.activity import client_ip

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


def build_me(db: Session, staff: StaffUser) -> Me:
    gym = db.get(Gym, staff.gym_id) if staff.gym_id else None
    subscription_read = None
    branch_ids = None
    if gym is not None:
        state = subscription.state(db, gym.id)
        subscription_read = SubscriptionRead(
            status=state.status,
            plan_name=state.plan_name,
            starts_on=state.starts_on,
            ends_on=state.ends_on,
            days_left=state.days_left,
            phase=state.phase,
            grace_ends_on=state.grace_ends_on,
            over_limit=state.over_limit,
        )
        if not staff.is_owner:
            rows = db.scalars(
                select(StaffBranchAccess.branch_id).where(
                    StaffBranchAccess.staff_user_id == staff.id
                )
            ).all()
            branch_ids = sorted(rows) or None

    # A platform admin's are /admin's own (app/core/admin_permissions.py).
    permissions = sorted(
        effective_permissions(is_owner=staff.is_owner, stored=staff.permissions)
        if gym is not None
        else admin_permissions.effective(staff)
        if staff.is_platform_admin
        else []
    )
    return Me(
        staff=StaffRead.model_validate(staff),
        gym=gym_read(gym) if gym else None,
        two_step_required=staff.is_platform_admin
        or (gym is not None and gym.config.require_two_step),
        permissions=permissions,
        branch_ids=branch_ids,
        subscription=subscription_read,
        support_whatsapp=settings.support_whatsapp,
        changelog_unread=changelog.unread(db, staff),
        language=staff.language or (gym.config.language if gym else "en"),
        own_language=staff.language,
        digits=gym.config.digits if gym else "western",
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


def _failed_login(
    db: Session,
    staff: StaffUser | None,
    key: str,
    request: Request,
    error: AppError = BAD_LOGIN,
) -> NoReturn:
    """Count a wrong try, kept even though the request fails, and refuse it."""
    if staff_auth.record(db, key, client_ip(request), succeeded=False) and staff:
        activity.record(
            db,
            gym_id=staff.gym_id,
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            action="staff.locked_out",
            entity="staff",
            entity_id=staff.id,
            request=request,
        )
    db.commit()
    raise error


def _check_can_sign_in(db: Session, staff: StaffUser) -> None:
    if not staff.is_active:
        raise AppError(403, "account_disabled", "This account has been disabled.")
    if staff.gym_id is not None:
        gym = db.get(Gym, staff.gym_id)
        if gym is not None and gym.status != GYM_ACTIVE:
            raise AppError(
                403,
                "gym_suspended",
                "This gym's account is suspended. Contact GymBhai.",
            )


def _signed_in(
    db: Session,
    staff: StaffUser,
    key: str,
    request: Request,
    response: Response,
    method: str | None = None,
) -> SessionResponse:
    staff_auth.record(db, key, client_ip(request), succeeded=True)
    issued = sessions.start(db, staff, request)
    activity.staff_action(
        db,
        staff,
        "staff.signed_in",
        entity="staff",
        entity_id=staff.id,
        changes={"two_step": method} if method else None,
        request=request,
    )
    db.commit()
    return _session_response(db, issued, response)


@router.post("/login", response_model=SessionResponse | TwoStepChallenge)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse | TwoStepChallenge:
    """Staff sign in with their email or phone and a password.

    With two-step sign-in on, the right password gets a challenge instead of a
    session: POST /auth/login/two-step with the code from the app.
    """
    key = staff_auth.canonical(payload.identifier)
    staff_auth.check(db, key, client_ip(request))
    staff = staff_auth.find_staff(db, key)
    if staff is None:
        burn_password_check()
        _failed_login(db, None, key, request)
    # One message for an unknown account and a wrong password, so the answer
    # never confirms who has an account.
    if not verify_password(payload.password, staff.password_hash):
        _failed_login(db, staff, key, request)
    _check_can_sign_in(db, staff)
    if staff.two_step_enabled:
        return TwoStepChallenge(
            two_step_token=create_two_step_token(staff_id=staff.id, identifier=key),
            expires_in=TWO_STEP_MINUTES * 60,
        )
    return _signed_in(db, staff, key, request, response)


@router.post("/login/two-step", response_model=SessionResponse)
def login_two_step(
    payload: TwoStepLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """The second step: a code from the authenticator app, or a recovery code.

    Wrong codes count against the same limit as wrong passwords.
    """
    try:
        claims = decode_two_step_token(payload.two_step_token)
    except TokenError as exc:
        raise AppError(401, exc.code, str(exc)) from exc
    staff_auth.check(db, claims.identifier, client_ip(request))
    staff = db.get(StaffUser, claims.staff_id)
    if staff is None or not staff.two_step_enabled:
        raise AppError(401, "two_step_expired", "Sign in again.")
    _check_can_sign_in(db, staff)
    method = two_step.check_code(db, staff, payload.code)
    if method is None:
        _failed_login(
            db,
            staff,
            claims.identifier,
            request,
            AppError(401, "bad_code", "That code is wrong or has expired."),
        )
    return _signed_in(db, staff, claims.identifier, request, response, method)


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


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, int]:
    """Forgot password: a code to the email or phone typed, if it has an account.

    The same answer either way, so it never confirms who has an account.
    """
    staff_auth.request_reset(db, payload.identifier, request)
    return {"expires_in": settings.password_reset_minutes * 60}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)
) -> Response:
    """A new password with the code. Every device is signed out; sign in again."""
    staff_auth.reset_password(
        db, payload.identifier, payload.code, payload.new_password, request
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _confirm_password(staff: StaffUser, password: str) -> None:
    if not verify_password(password, staff.password_hash):
        raise AppError(403, "wrong_password", "That is not your current password.")


@router.get("/two-step", response_model=TwoStepStatus)
def two_step_status(
    staff: StaffUser = Depends(current_staff), db: Session = Depends(get_db)
) -> TwoStepStatus:
    return TwoStepStatus(
        enabled=staff.two_step_enabled,
        required=two_step.is_required(db, staff),
        recovery_codes_left=two_step.recovery_codes_left(db, staff),
    )


@router.post("/two-step/setup", response_model=TwoStepSetupRead)
def start_two_step_setup(
    payload: PasswordConfirm,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
) -> TwoStepSetupRead:
    """A new secret for the authenticator app; on once /enable gets a code."""
    _confirm_password(staff, payload.password)
    setup = two_step.start_setup(staff)
    db.commit()
    return TwoStepSetupRead(secret=setup.secret, uri=setup.uri)


@router.post("/two-step/enable", response_model=RecoveryCodes)
def enable_two_step(
    payload: TwoStepEnable,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
) -> RecoveryCodes:
    """On, with a first code from the app. The recovery codes are shown once."""
    codes = two_step.enable(db, staff, payload.code)
    activity.staff_action(
        db,
        staff,
        "staff.two_step_enabled",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    live.staff_changed(db, staff.gym_id)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/two-step/recovery-codes", response_model=RecoveryCodes)
def new_recovery_codes(
    payload: PasswordConfirm,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
) -> RecoveryCodes:
    """Ten new recovery codes; the old ones stop working."""
    _confirm_password(staff, payload.password)
    if not staff.two_step_enabled:
        raise AppError(409, "two_step_off", "Two-step sign-in is off.")
    codes = two_step.new_recovery_codes(db, staff)
    activity.staff_action(
        db,
        staff,
        "staff.recovery_codes_renewed",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/two-step/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_two_step(
    payload: PasswordConfirm,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
) -> Response:
    """Off, unless this account must use it."""
    _confirm_password(staff, payload.password)
    if two_step.is_required(db, staff):
        raise AppError(
            403, "two_step_required", "This account must use two-step sign-in."
        )
    two_step.disable(db, staff)
    activity.staff_action(
        db,
        staff,
        "staff.two_step_disabled",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    live.staff_changed(db, staff.gym_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[DeviceSession])
def list_sessions(
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    current: StaffSession = Depends(current_session),
) -> list[DeviceSession]:
    """The devices signed in to your account (My account → Devices)."""
    return [
        DeviceSession(
            id=row.id,
            user_agent=row.user_agent,
            ip=row.ip,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            current=row.id == current.id,
        )
        for row in sessions.live_sessions(db, staff)
    ]


@router.post("/sessions/sign-out-others", response_model=SignedOut)
def sign_out_others(
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    current: StaffSession = Depends(current_session),
) -> SignedOut:
    """Every device but this one: a lost phone, a shared PC at the desk."""
    count = sessions.revoke_all(db, staff, keep=current.id)
    activity.staff_action(
        db,
        staff,
        "staff.signed_out_others",
        entity="staff",
        entity_id=staff.id,
        changes={"devices": count},
        request=request,
    )
    # Their open screens find out at once, not at their next click.
    live.staff_changed(db, staff.gym_id)
    db.commit()
    return SignedOut(signed_out=count)


@router.post("/sessions/{session_id}/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out_device(
    session_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(current_staff),
    current: StaffSession = Depends(current_session),
) -> Response:
    """One of your other devices. Another account's sessions are not found."""
    row = db.get(StaffSession, session_id)
    if row is None or row.staff_user_id != staff.id or row.revoked_at is not None:
        raise not_found("No such device.")
    if row.id == current.id:
        raise AppError(409, "current_session", "Use Sign out for this device.")
    row.revoked_at = utcnow()
    activity.staff_action(
        db,
        staff,
        "staff.device_signed_out",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    live.staff_changed(db, staff.gym_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/me/language", response_model=Me)
def set_language(
    payload: LanguageIn,
    staff: StaffUser = Depends(current_staff),
    db: Session = Depends(get_db),
) -> Me:
    """Their own language (§16.6); null follows the gym's."""
    staff.language = payload.language
    db.commit()
    return build_me(db, staff)


@router.get("/me", response_model=Me)
def me(staff: StaffUser = Depends(current_staff), db: Session = Depends(get_db)) -> Me:
    return build_me(db, staff)
