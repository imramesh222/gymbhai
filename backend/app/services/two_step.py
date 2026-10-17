"""Two-step sign-in with an authenticator app (PLAN.md §16.1).

* Required for platform admins. Optional for gym staff, unless the owner
  requires it for everyone in the gym (gym setting `require_two_step`).
* Someone who must use it and hasn't set it up yet can sign in, but only to
  set it up: every other route refuses them (app/api/deps.py).
* Turning it on gives 10 single-use recovery codes, for a lost phone. Only
  their hashes are kept, so they are shown once.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import settings
from app.core.errors import AppError
from app.core.time import utcnow
from app.models.gym import Gym
from app.models.staff import StaffRecoveryCode, StaffUser

RECOVERY_CODES = 10
# No 0/o, 1/l/i: these get read off paper and typed on a phone.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

METHOD_APP = "app"
METHOD_RECOVERY = "recovery_code"


def is_required(db: Session, staff: StaffUser) -> bool:
    if staff.is_platform_admin:
        return True
    gym = db.get(Gym, staff.gym_id) if staff.gym_id else None
    return gym is not None and gym.config.require_two_step


def setup_pending(db: Session, staff: StaffUser) -> bool:
    """Must use two-step sign-in and hasn't set it up: may only set it up."""
    return not staff.two_step_enabled and is_required(db, staff)


def setup_pending_error() -> AppError:
    return AppError(
        403,
        "two_step_setup_required",
        "Set up two-step sign-in before you continue.",
    )


@dataclass(frozen=True)
class Setup:
    secret: str
    uri: str


def start_setup(staff: StaffUser) -> Setup:
    """A new secret for the authenticator app. Not in use until `enable`."""
    if staff.two_step_enabled:
        raise AppError(409, "two_step_on", "Two-step sign-in is already on.")
    staff.totp_nonce = secrets.token_hex(16)
    secret = totp.secret_for(staff.id, staff.totp_nonce)
    account = staff.email or staff.phone or staff.name
    return Setup(totp.text_secret(secret), totp.provisioning_uri(secret, account))


def _recovery_hash(code: str) -> str:
    normalised = "".join(ch for ch in code.lower() if ch.isalnum())
    message = f"recovery:{normalised}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def new_recovery_codes(db: Session, staff: StaffUser) -> list[str]:
    """Replace every recovery code with 10 new ones, returned this once."""
    db.execute(
        delete(StaffRecoveryCode).where(StaffRecoveryCode.staff_user_id == staff.id)
    )
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    db.add_all(
        StaffRecoveryCode(staff_user_id=staff.id, code_hash=_recovery_hash(code))
        for code in codes
    )
    return codes


def enable(db: Session, staff: StaffUser, code: str) -> list[str]:
    """Turn it on with a first code from the app. Returns the recovery codes."""
    if staff.two_step_enabled:
        raise AppError(409, "two_step_on", "Two-step sign-in is already on.")
    if staff.totp_nonce is None:
        raise AppError(409, "two_step_not_started", "Start setting it up first.")
    secret = totp.secret_for(staff.id, staff.totp_nonce)
    step = totp.verify(secret, code, after_step=None)
    if step is None:
        raise AppError(401, "bad_code", "That code is wrong or has expired.")
    staff.totp_enabled_at = utcnow()
    staff.totp_last_step = step
    return new_recovery_codes(db, staff)


def disable(db: Session, staff: StaffUser) -> None:
    """Off, and the recovery codes gone. Also how an owner or we reset it."""
    staff.totp_nonce = None
    staff.totp_enabled_at = None
    staff.totp_last_step = None
    db.execute(
        delete(StaffRecoveryCode).where(StaffRecoveryCode.staff_user_id == staff.id)
    )


def check_code(db: Session, staff: StaffUser, code: str) -> str | None:
    """How they proved it: METHOD_APP or METHOD_RECOVERY, or None if wrong.

    A code from the app works once; a recovery code is used up.
    """
    if not staff.two_step_enabled or staff.totp_nonce is None:
        return None
    secret = totp.secret_for(staff.id, staff.totp_nonce)
    step = totp.verify(secret, code, after_step=staff.totp_last_step)
    if step is not None:
        staff.totp_last_step = step
        return METHOD_APP
    recovery = db.scalars(
        select(StaffRecoveryCode)
        .where(
            StaffRecoveryCode.staff_user_id == staff.id,
            StaffRecoveryCode.code_hash == _recovery_hash(code),
            StaffRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    ).first()
    if recovery is None:
        return None
    recovery.used_at = utcnow()
    return METHOD_RECOVERY


def recovery_codes_left(db: Session, staff: StaffUser) -> int:
    return db.scalar(
        select(func.count())
        .select_from(StaffRecoveryCode)
        .where(
            StaffRecoveryCode.staff_user_id == staff.id,
            StaffRecoveryCode.used_at.is_(None),
        )
    )
