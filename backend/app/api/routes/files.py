"""Uploaded files, served only through signed, expiring links (PLAN.md §11)."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.errors import not_found
from app.services import storage

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}")
def get_file(
    key: str,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query(max_length=64)],
) -> Response:
    """The signature is the permission: it was issued to someone allowed to see it."""
    if not storage.verify(key, exp, sig):
        raise not_found("This link has expired.")
    data = storage.read(key)
    if data is None:
        raise not_found("File not found.")
    extension = key.rsplit(".", 1)[-1]
    return Response(
        content=data,
        media_type=storage.CONTENT_TYPES.get(extension, "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
