"""Errors the API returns on purpose.

Every error body carries a stable `code` alongside the English `detail`. The
frontend translates by code (`errors.<code>` in its translation files), so
adding Nepali later never means parsing English sentences.
"""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers
        self.extra = extra


def not_found(message: str = "Not found.") -> AppError:
    """Also the answer for another gym's records: never confirm they exist."""
    return AppError(404, "not_found", message)


def unauthorized(
    code: str = "not_authenticated", message: str = "Sign in."
) -> AppError:
    return AppError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status,
        content={"detail": exc.message, "code": exc.code, **exc.extra},
        headers=exc.headers,
    )


def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """422 with the offending field names, so the form can point at them."""
    assert isinstance(exc, RequestValidationError)
    fields = []
    for error in exc.errors():
        # loc is ("body", "owner_phone") for a body field.
        loc = [str(part) for part in error.get("loc", ()) if part != "body"]
        fields.append({"field": ".".join(loc), "type": error.get("type")})
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Some fields need attention.",
            "code": "validation_error",
            "fields": fields,
        },
    )
