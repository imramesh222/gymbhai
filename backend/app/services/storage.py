"""Uploaded files: member photos, gym logos, payment QR images (PLAN.md §3).

Files are stored under a key such as `gyms/<gym_id>/members/<uuid>.jpg` and
never exposed by a permanent public link: they are handed out as signed URLs
that expire (§11), served by GET /api/v1/files/<key>.

Local disk in development; any S3-compatible bucket (Cloudflare R2) in
production, behind the same three functions: put, read, delete. Files are
still served through the API with signed links either way, so the bucket
itself stays private.
"""

import hashlib
import hmac
import time
import uuid
from functools import cache
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


@cache
def _s3():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )


def _content_type(key: str) -> str:
    return CONTENT_TYPES.get(key.rsplit(".", 1)[-1], "application/octet-stream")


def put(key: str, data: bytes) -> str:
    if settings.storage_backend == "s3":
        _s3().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=_content_type(key),
        )
        return key
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def read(key: str) -> bytes | None:
    if settings.storage_backend == "s3":
        from botocore.exceptions import ClientError

        try:
            return _s3().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
    path = _path(key)
    return path.read_bytes() if path.is_file() else None


def delete(key: str | None) -> None:
    if not key:
        return
    if settings.storage_backend == "s3":
        _s3().delete_object(Bucket=settings.s3_bucket, Key=key)
        return
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
