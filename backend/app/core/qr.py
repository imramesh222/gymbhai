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


@dataclass(frozen=True)
class Scanned:
    kind: str  # "app" or "card"
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
    if len(parts) != 4 or parts[0] != "gb1":
        return None
    try:
        member_id = uuid.UUID(hex=parts[1])
        window = int(parts[2])
    except ValueError:
        return None
    return Scanned(kind="app", member_id=member_id, window=window, signature=parts[3])


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
