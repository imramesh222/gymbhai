import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.router import include_all
from app.core.config import settings
from app.core.errors import AppError, app_error_handler, validation_error_handler

logging.basicConfig(level=logging.INFO)

if settings.sentry_dsn:
    import sentry_sdk

    # Errors only; no request bodies, which hold phone numbers and payments.
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,
        traces_sample_rate=0.0,
    )

# No CORS middleware: the browser reaches the API through the Next.js server's
# /api proxy, so every request is same-origin.
app = FastAPI(
    title=f"{settings.app_name} API",
    description="Gym membership, payments and check-ins for gyms in Nepal.",
    version="0.1.0",
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

include_all(app)
