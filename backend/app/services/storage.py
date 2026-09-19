"""Uploaded files: member photos, gym logos, payment QR images (PLAN.md §3).

Files are stored under a key such as `gyms/<gym_id>/members/<uuid>.jpg` and
never exposed by a permanent public link: they are handed out as signed URLs
that expire (§11), served by GET /api/v1/files/<key>.

Local disk in development. Production swaps in S3-compatible storage behind
the same three functions (see PLAN.md §13).
"""

import hashlib
import hmac
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from app.core.config import settings
from app.core.errors import AppError

MAX_BYTES = 5 * 1024 * 1024
URL_TTL_SECONDS = 6 * 3600

# Sniffed from the bytes, never trusted from the upload's own Content-Type.
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)

CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def sniff_image(data: bytes) -> str:
    """The file extension for an image we accept, or AppError."""
    if len(data) > MAX_BYTES:
        raise AppError(413, "file_too_large", "Images must be 5 MB or smaller.")
    for magic, _, extension in _SIGNATURES:
        if data.startswith(magic):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise AppError(415, "unsupported_image", "Upload a JPEG, PNG or WebP image.")


def _root() -> Path:
    return Path(settings.media_root).resolve()


def _path(key: str) -> Path:
    path = (_root() / key).resolve()
    # A key is ours, but check anyway: nothing may escape the media root.
    if _root() not in path.parents:
        raise AppError(400, "bad_key", "Invalid file.")
    return path


def new_key(gym_id: uuid.UUID, folder: str, extension: str) -> str:
    return f"gyms/{gym_id}/{folder}/{uuid.uuid4().hex}.{extension}"


def put(key: str, data: bytes) -> str:
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def read(key: str) -> bytes | None:
    path = _path(key)
    return path.read_bytes() if path.is_file() else None


def delete(key: str | None) -> None:
    if key:
        _path(key).unlink(missing_ok=True)


def _signature(key: str, expires: int) -> str:
    message = f"{key}:{expires}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()[
        :32
    ]


def signed_url(key: str | None, ttl: int = URL_TTL_SECONDS) -> str | None:
    if not key:
        return None
    # Rounded up to the hour so a page's image URLs stay the same for a while
    # and the browser cache can do its job.
    expires = (int(time.time()) + ttl) // 3600 * 3600 + 3600
    return (
        f"{settings.api_v1_prefix}/files/{quote(key)}"
        f"?exp={expires}&sig={_signature(key, expires)}"
    )


def verify(key: str, expires: int, signature: str) -> bool:
    if expires < time.time():
        return False
    return hmac.compare_digest(_signature(key, expires), signature)
