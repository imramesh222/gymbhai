"""The VAPID key pair that signs our Web Push messages (PLAN.md §16.3, 8.3).

The private key is settings.vapid_private_key: base64url of the raw 32-byte
P-256 key. The browser subscribes with the public key, so changing the key
means every member subscribes again.
"""

import base64
from functools import lru_cache

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core.config import settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def generate() -> str:
    """A new private key, in the form VAPID_PRIVATE_KEY takes."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64(key.private_numbers().private_value.to_bytes(32, "big"))


@lru_cache
def _public(private: str) -> str:
    key = ec.derive_private_key(int.from_bytes(_unb64(private), "big"), ec.SECP256R1())
    point = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return _b64(point)


def public_key() -> str | None:
    """What the member app subscribes with; None when push is not set up."""
    return _public(settings.vapid_private_key) if settings.vapid_private_key else None
