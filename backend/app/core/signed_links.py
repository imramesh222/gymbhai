"""Links that work without signing in, for a while (PLAN.md §16.3, 8.4).

A receipt shared on WhatsApp opens for whoever taps it, so the link carries an
expiry and an HMAC of what it opens; changing either breaks it. SECRET_KEY
signs them: rotating it ends every link at once.
"""

import base64
import hashlib
import hmac
import uuid

from app.core.config import settings
from app.core.time import utcnow


def _signature(kind: str, thing: uuid.UUID, expires: int) -> str:
    message = f"{kind}:{thing}:{expires}".encode()
    digest = hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode()  # 144 bits, no padding


def sign(kind: str, thing: uuid.UUID, days: int) -> tuple[int, str]:
    expires = int(utcnow().timestamp()) + days * 24 * 60 * 60
    return expires, _signature(kind, thing, expires)


def valid(kind: str, thing: uuid.UUID, expires: int, signature: str) -> bool:
    if expires < utcnow().timestamp():
        return False
    return hmac.compare_digest(_signature(kind, thing, expires), signature)
