"""Authenticator-app codes for two-step sign-in (TOTP, RFC 6238; PLAN.md §16.1).

The shared secret is never stored. Each account keeps a random nonce, and its
secret is HMAC(TOTP_KEY, account id and nonce), so the database alone can't
produce codes. Starting setup again picks a new nonce, which retires the old
secret.

Codes are the usual 6 digits every 30 seconds with SHA-1, which is what
Google Authenticator, Microsoft Authenticator and the rest all support.
"""

import base64
import datetime as dt
import hashlib
import hmac
import struct
import uuid
from urllib.parse import quote, urlencode

from app.core.config import settings
from app.core.time import utcnow

STEP_SECONDS = 30
DIGITS = 6
# A phone clock a little fast or slow still works: one step either side.
DRIFT_STEPS = 1
ISSUER = "GymBhai"


def _key() -> bytes:
    return (settings.totp_key or settings.secret_key).encode()


def secret_for(account_id: uuid.UUID, nonce: str) -> bytes:
    """The 20-byte secret an authenticator app is given for this account."""
    message = f"totp:{account_id}:{nonce}".encode()
    return hmac.new(_key(), message, hashlib.sha256).digest()[:20]


def code_at(secret: bytes, step: int) -> str:
    """The code for one 30-second step (RFC 4226 HOTP with the step as counter)."""
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def step_at(moment: dt.datetime | None = None) -> int:
    return int((moment or utcnow()).timestamp()) // STEP_SECONDS


def verify(
    secret: bytes, code: str, *, after_step: int | None, now: dt.datetime | None = None
) -> int | None:
    """The step `code` belongs to, or None if it is wrong.

    A step at or before `after_step` (the last one used) is refused, so a code
    seen over someone's shoulder can't be used a second time.
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    current = step_at(now)
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        if after_step is not None and step <= after_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def text_secret(secret: bytes) -> str:
    """The secret as people type it into an app: base32, no padding."""
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def provisioning_uri(secret: bytes, account: str) -> str:
    """The otpauth:// link the setup QR code carries."""
    label = quote(f"{ISSUER}:{account}")
    query = urlencode(
        {
            "secret": text_secret(secret),
            "issuer": ISSUER,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"
