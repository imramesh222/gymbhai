"""Secrets we must read back: a gym's merchant keys (PLAN.md §20.2).

Unlike passwords these can't be hashed: each payment is signed with them. So
they are encrypted with AES-GCM under GATEWAY_KEY (SECRET_KEY locally), with a
fresh nonce each time and the row they belong to as associated data: copied
into another gym's row, they no longer open. The database alone is not enough
to read them.
"""

import base64
import hashlib
import json
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

VERSION = "v1"


class Unreadable(Exception):
    """Sealed with another key, or not for this row."""


def _cipher() -> AESGCM:
    key = (settings.gateway_key or settings.secret_key).encode()
    return AESGCM(hashlib.sha256(b"gymbhai-sealed:" + key).digest())


def seal(values: dict[str, str], owner: uuid.UUID) -> str:
    nonce = os.urandom(12)
    data = _cipher().encrypt(nonce, json.dumps(values).encode(), owner.bytes)
    return f"{VERSION}:{base64.urlsafe_b64encode(nonce + data).decode()}"


def open_sealed(sealed: str, owner: uuid.UUID) -> dict[str, str]:
    version, _, body = sealed.partition(":")
    if version != VERSION:
        raise Unreadable(version)
    raw = base64.urlsafe_b64decode(body)
    try:
        values = json.loads(_cipher().decrypt(raw[:12], raw[12:], owner.bytes))
    except InvalidTag as exc:
        raise Unreadable("wrong key or row") from exc
    return {str(k): str(v) for k, v in values.items()}
