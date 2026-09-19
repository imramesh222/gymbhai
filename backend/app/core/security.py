"""Passwords, access tokens and refresh tokens (PLAN.md §11).

An access token is a short-lived JWT naming the staff member, their gym and
the session it belongs to. It proves identity only: permissions and branch
access are read from the database on every request, so removing a permission
takes effect on the next request, not at the next sign-in.

A refresh token is an opaque random string in an httpOnly cookie. Only its
SHA-256 is stored, so a database leak does not hand out live sessions.
"""

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from functools import cache

import bcrypt
import jwt

from app.core.config import settings
from app.core.time import utcnow

ALGORITHM = "HS256"
ACCESS = "access"
MEMBER = "member"
# bcrypt ignores everything past 72 bytes, which would make two different long
# passwords equivalent. Longer ones are refused instead.
MAX_PASSWORD_BYTES = 72


class TokenError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except ValueError:
        # A malformed hash reads as a wrong password, never as a crash.
        return False


@cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check() -> None:
    """Spend the time a real check would, for sign-ins to unknown accounts.

    Without it, "no such account" answers in a millisecond and "wrong password"
    in a quarter of a second, and the difference lists who has an account.
    """
    verify_password("not-a-real-password", _dummy_hash())


@dataclass(frozen=True)
class AccessClaims:
    staff_id: uuid.UUID
    gym_id: uuid.UUID | None
    session_id: uuid.UUID


def create_access_token(
    *, staff_id: uuid.UUID, gym_id: uuid.UUID | None, session_id: uuid.UUID
) -> str:
    now = utcnow()
    payload = {
        "typ": ACCESS,
        "sub": str(staff_id),
        "gym": str(gym_id) if gym_id else None,
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(
            (now + dt.timedelta(minutes=settings.access_token_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("session_expired", "Your session has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid_token", "Invalid session token.") from exc

    if payload.get("typ") != ACCESS:
        raise TokenError("invalid_token", "Invalid session token.")
    try:
        return AccessClaims(
            staff_id=uuid.UUID(payload["sub"]),
            gym_id=uuid.UUID(payload["gym"]) if payload.get("gym") else None,
            session_id=uuid.UUID(payload["sid"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("invalid_token", "Invalid session token.") from exc


def create_member_token(
    *, member_id: uuid.UUID, gym_id: uuid.UUID, session_id: uuid.UUID
) -> str:
    """A member app token. Its own type, so it can never pass as a staff one."""
    now = utcnow()
    payload = {
        "typ": MEMBER,
        "sub": str(member_id),
        "gym": str(gym_id),
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(
            (now + dt.timedelta(minutes=settings.access_token_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


@dataclass(frozen=True)
class MemberClaims:
    member_id: uuid.UUID
    gym_id: uuid.UUID
    session_id: uuid.UUID


def decode_member_token(token: str) -> MemberClaims:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("session_expired", "Your session has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid_token", "Invalid session token.") from exc
    if payload.get("typ") != MEMBER:
        raise TokenError("invalid_token", "Invalid session token.")
    try:
        return MemberClaims(
            member_id=uuid.UUID(payload["sub"]),
            gym_id=uuid.UUID(payload["gym"]),
            session_id=uuid.UUID(payload["sid"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("invalid_token", "Invalid session token.") from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
