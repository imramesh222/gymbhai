"""Staff sign-in: finding the account, the limits on guessing, and "forgot
password" codes (PLAN.md §16.1).

Every try is recorded, for unknown accounts as well as real ones, so the
answer never shows which accounts exist:

* LOGIN_MAX_FAILURES wrong tries for one email or phone within
  LOGIN_WINDOW_MINUTES and it must wait. A successful sign-in starts its count
  again.
* LOGIN_MAX_FAILURES_PER_IP wrong tries from one address in the same window
  and that address must wait, whichever accounts it was trying.

A try refused by a limit is not recorded, so a locked account opens again on
time however often someone keeps knocking.
"""

import datetime as dt
import hashlib
import hmac
import logging
import math
import secrets
import uuid

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.phone import normalize_phone
from app.core.security import hash_password
from app.core.time import utcnow
from app.models.activity import ACTOR_STAFF
from app.models.messaging import SMS_OTP, SmsMessage
from app.models.staff import LoginAttempt, StaffPasswordReset, StaffUser
from app.services import activity, email, sessions
from app.services.activity import client_ip
from app.services.sms import service as sms

log = logging.getLogger("gymbhai.staff_auth")


def canonical(identifier: str) -> str:
    """The form accounts are stored in: email lower-cased, phone normalised.

    Anything that is neither still gets a stable form, so the limits count it.
    """
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier.lower()[:254]
    try:
        return normalize_phone(identifier)
    except ValueError:
        return identifier.lower()[:254]


def find_staff(db: Session, key: str) -> StaffUser | None:
    """The account for a canonical email or phone, if there is one."""
    column = StaffUser.email if "@" in key else StaffUser.phone
    return db.scalars(select(StaffUser).where(column == key)).first()


def _window_start() -> dt.datetime:
    return utcnow() - dt.timedelta(minutes=settings.login_window_minutes)


def _recent_failures(db: Session, *conditions, limit: int) -> list[dt.datetime]:
    """When the latest `limit` failures matching `conditions` happened, newest first."""
    return list(
        db.scalars(
            select(LoginAttempt.at)
            .where(LoginAttempt.succeeded.is_(False), *conditions)
            .order_by(LoginAttempt.at.desc())
            .limit(limit)
        )
    )


def _account_failures(db: Session, key: str) -> list[dt.datetime]:
    since = _window_start()
    last_success = db.scalar(
        select(func.max(LoginAttempt.at)).where(
            LoginAttempt.identifier == key,
            LoginAttempt.succeeded.is_(True),
            LoginAttempt.at >= since,
        )
    )
    conditions = [LoginAttempt.identifier == key, LoginAttempt.at >= since]
    if last_success is not None:
        conditions.append(LoginAttempt.at > last_success)
    return _recent_failures(db, *conditions, limit=settings.login_max_failures)


def _ip_failures(db: Session, ip: str) -> list[dt.datetime]:
    return _recent_failures(
        db,
        LoginAttempt.ip == ip,
        LoginAttempt.at >= _window_start(),
        limit=settings.login_max_failures_per_ip,
    )


def check(db: Session, key: str, ip: str | None) -> None:
    """Refuse the try, before any password is checked, if a limit is reached."""
    window = dt.timedelta(minutes=settings.login_window_minutes)
    waits = []
    failures = _account_failures(db, key)
    if len(failures) >= settings.login_max_failures:
        waits.append(failures[-1] + window)
    if ip:
        failures = _ip_failures(db, ip)
        if len(failures) >= settings.login_max_failures_per_ip:
            waits.append(failures[-1] + window)
    if waits:
        seconds = max(1, math.ceil((max(waits) - utcnow()).total_seconds()))
        raise AppError(
            429,
            "too_many_attempts",
            "Too many wrong tries. Wait a few minutes and try again.",
            headers={"Retry-After": str(seconds)},
        )


def record(db: Session, key: str, ip: str | None, *, succeeded: bool) -> bool:
    """Write one try. True when this failure is the one that locks the account."""
    db.add(LoginAttempt(identifier=key, ip=ip, succeeded=succeeded, at=utcnow()))
    db.flush()
    if succeeded:
        return False
    return len(_account_failures(db, key)) == settings.login_max_failures


# --- forgot password ------------------------------------------------------------

RESET_REDACTED = "Password reset code (hidden)"


def _reset_hash(staff_id: uuid.UUID, code: str) -> str:
    message = f"password-reset:{staff_id}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _too_many_resets(db: Session, key: str, ip: str | None) -> bool:
    """The member sign-in code limits (§11): each code may cost us an SMS."""
    since = utcnow() - dt.timedelta(minutes=settings.otp_window_minutes)

    def count(*conditions) -> int:
        return db.scalar(
            select(func.count())
            .select_from(StaffPasswordReset)
            .where(StaffPasswordReset.created_at >= since, *conditions)
        )

    if count(StaffPasswordReset.identifier == key) >= settings.otp_per_destination:
        return True
    return bool(ip) and count(StaffPasswordReset.ip == ip) >= settings.otp_per_ip


def _send_reset_code(db: Session, staff: StaffUser, key: str, code: str) -> None:
    """To the email or phone that was typed. Failures are logged, not shown:
    the answer to the request must not differ for real accounts."""
    minutes = settings.password_reset_minutes
    text = (
        f"{code} is your GymBhai password reset code. It expires in {minutes} "
        "minutes. If you didn't ask for it, ignore this message."
    )
    if "@" in key:
        try:
            email.send(key, "Your GymBhai password reset code", text)
        except email.EmailError:
            log.exception("password reset email to staff %s failed", staff.id)
        return
    if staff.gym_id is None:
        # Platform admins have no gym to file an SMS under; they use email.
        return
    message = SmsMessage(
        gym_id=staff.gym_id, to=key, body=text, kind=SMS_OTP, segments=1
    )
    db.add(message)
    db.flush()
    if not sms.send_now(db, message):
        log.error("password reset SMS to staff %s failed: %s", staff.id, message.error)
    # The gym's SMS log is readable by staff: a code left in it would let them
    # set the owner's password.
    message.body = RESET_REDACTED


def request_reset(db: Session, identifier: str, request: Request | None) -> None:
    """Send a code if the email or phone belongs to an active account.

    The answer is the same whether or not it does, so this never confirms who
    has an account.
    """
    key = canonical(identifier)
    ip = client_ip(request)
    if _too_many_resets(db, key, ip):
        raise AppError(
            429, "too_many_codes", "Too many codes asked for. Wait a few minutes."
        )
    staff = find_staff(db, key)
    if staff is not None and not staff.is_active:
        staff = None
    code = settings.otp_test_code or f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        StaffPasswordReset(
            staff_user_id=staff.id if staff else None,
            identifier=key,
            code_hash=_reset_hash(staff.id, code) if staff else None,
            expires_at=utcnow() + dt.timedelta(minutes=settings.password_reset_minutes),
            ip=ip,
        )
    )
    if staff is not None:
        _send_reset_code(db, staff, key, code)
    db.commit()


def reset_password(
    db: Session,
    identifier: str,
    code: str,
    new_password: str,
    request: Request | None,
) -> None:
    """Set a new password with a code, and sign the account out everywhere."""
    key = canonical(identifier)
    wrong = AppError(401, "bad_code", "That code is wrong or has expired.")
    row = db.scalars(
        select(StaffPasswordReset)
        .where(StaffPasswordReset.identifier == key)
        .order_by(StaffPasswordReset.expires_at.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if (
        row is None
        or row.staff_user_id is None
        or row.code_hash is None
        or row.consumed_at is not None
        or row.expires_at <= utcnow()
        or row.attempts >= settings.otp_max_attempts
    ):
        raise wrong
    if not hmac.compare_digest(row.code_hash, _reset_hash(row.staff_user_id, code)):
        row.attempts += 1
        db.commit()
        raise wrong
    staff = db.get(StaffUser, row.staff_user_id)
    if staff is None or not staff.is_active:
        raise wrong

    row.consumed_at = utcnow()
    staff.password_hash = hash_password(new_password)
    sessions.revoke_all(db, staff)
    # Proving who they are starts the sign-in count again (§16.1), so the
    # owner of an account someone was guessing at is not left waiting.
    ip = client_ip(request)
    for login_key in {staff.email, staff.phone} - {None}:
        record(db, login_key, ip, succeeded=True)
    activity.record(
        db,
        gym_id=staff.gym_id,
        actor_type=ACTOR_STAFF,
        actor_id=staff.id,
        action="staff.password_reset_by_code",
        entity="staff",
        entity_id=staff.id,
        request=request,
    )
    db.commit()
