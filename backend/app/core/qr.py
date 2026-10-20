"""Member QR codes (PLAN.md §4.2).

Two forms of one identity:

* In the app, a code that changes every 30 seconds:
      gb1.<member id, 32 hex>.<window>.<signature>
  The phone derives it from a per-member key handed over at sign-in, so it
  works with no mobile data — only the scanner needs the internet. A
  screenshot stops working within a minute.

* On a printed card, a static code:
      gbc.<card token>
  Reissuing the card makes a new token; the old card stops working at once.

* In the app since §19.2, the same changing code signed with Ed25519:
      gb2.<member id, 32 hex>.<window>.<signature, 86 base64url>
  A kiosk holding only the public keys can check it offline but never make
  one, which an HMAC can't offer: whatever checks an HMAC can forge it. The
  server accepts both; apps sign gb2 once they have the key.

The app key is derived from the member's secret and qr_version, so bumping the
version (lost phone, suspected sharing) invalidates every old code.

frontend/src/lib/memberQr.ts computes the same codes; keep the two in step.
"""

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

WINDOW_SECONDS = 30
# Accept the current window and one either side, for clock drift (§4.2).
DRIFT_WINDOWS = 1
SIGNATURE_CHARS = 16


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def app_key(qr_secret: str, qr_version: int) -> str:
    """The key the member's phone signs with. Changes when qr_version does."""
    digest = hmac.new(
        bytes.fromhex(qr_secret), f"gb1:v{qr_version}".encode(), hashlib.sha256
    ).digest()
    return _b64(digest)


def _key_bytes(key: str) -> bytes:
    return base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))


def window_at(unix_seconds: float) -> int:
    return int(unix_seconds // WINDOW_SECONDS)


def signature(key: str, member_hex: str, window: int) -> str:
    digest = hmac.new(
        _key_bytes(key), f"{member_hex}.{window}".encode(), hashlib.sha256
    ).digest()
    return _b64(digest)[:SIGNATURE_CHARS]


def app_code(member_id: uuid.UUID, key: str, window: int) -> str:
    return f"gb1.{member_id.hex}.{window}.{signature(key, member_id.hex, window)}"


def card_code(card_token: str) -> str:
    return f"gbc.{card_token}"


# --- gb2: Ed25519 (PLAN.md §19.2) ---------------------------------------------------


def signing_key(qr_secret: str, qr_version: int) -> str:
    """The Ed25519 private key (its 32-byte seed) the phone signs gb2 with.
    Changes when qr_version does, like the gb1 key."""
    seed = hmac.new(
        bytes.fromhex(qr_secret), f"gb2:v{qr_version}".encode(), hashlib.sha256
    ).digest()
    return _b64(seed)


def public_key(qr_secret: str, qr_version: int) -> str:
    """What a kiosk checks gb2 codes with: it can't make one from it."""
    private = Ed25519PrivateKey.from_private_bytes(
        _key_bytes(signing_key(qr_secret, qr_version))
    )
    return _b64(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def app_code2(member_id: uuid.UUID, key: str, window: int) -> str:
    private = Ed25519PrivateKey.from_private_bytes(_key_bytes(key))
    signed = private.sign(f"{member_id.hex}.{window}".encode())
    return f"gb2.{member_id.hex}.{window}.{_b64(signed)}"


@dataclass(frozen=True)
class Scanned:
    kind: str  # "app" (gb1), "app2" (gb2) or "card"
    member_id: uuid.UUID | None = None
    window: int | None = None
    signature: str | None = None
    card_token: str | None = None


def parse(code: str) -> Scanned | None:
    """What a scanned string claims to be. None if it is not one of ours."""
    code = code.strip()
    if code.startswith("gbc."):
        token = code[4:]
        return Scanned(kind="card", card_token=token) if 8 <= len(token) <= 64 else None
    parts = code.split(".")
    if len(parts) != 4 or parts[0] not in ("gb1", "gb2"):
        return None
    try:
        member_id = uuid.UUID(hex=parts[1])
        window = int(parts[2])
    except ValueError:
        return None
    return Scanned(
        kind="app" if parts[0] == "gb1" else "app2",
        member_id=member_id,
        window=window,
        signature=parts[3],
    )


def verify_app_code(
    scanned: Scanned, qr_secret: str, qr_version: int, now: float | None = None
) -> bool:
    assert scanned.kind == "app" and scanned.member_id and scanned.window is not None
    current = window_at(now if now is not None else time.time())
    if abs(scanned.window - current) > DRIFT_WINDOWS:
        return False
    expected = signature(
        app_key(qr_secret, qr_version), scanned.member_id.hex, scanned.window
    )
    return hmac.compare_digest(expected, scanned.signature or "")


def verify_app_code2(
    scanned: Scanned, qr_secret: str, qr_version: int, now: float | None = None
) -> bool:
    assert scanned.kind == "app2" and scanned.member_id and scanned.window is not None
    current = window_at(now if now is not None else time.time())
    if abs(scanned.window - current) > DRIFT_WINDOWS:
        return False
    try:
        signed = _key_bytes(scanned.signature or "")
        Ed25519PublicKey.from_public_bytes(
            _key_bytes(public_key(qr_secret, qr_version))
        ).verify(signed, f"{scanned.member_id.hex}.{scanned.window}".encode())
    except (InvalidSignature, ValueError):
        return False
    return True
