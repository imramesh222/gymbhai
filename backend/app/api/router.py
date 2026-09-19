"""Every router the app serves, and where.

Kept as an explicit list because the regression tests walk it: FastAPI nests
included routers in private wrapper objects, so `app.routes` is not a reliable
way to enumerate endpoints.
"""

from fastapi import APIRouter, FastAPI

from app.api.routes import (
    auth,
    branches,
    door,
    files,
    gym,
    health,
    member_app,
    members,
    memberships,
    messaging,
    payment_methods,
    payment_requests,
    payments,
    plans,
    staff,
)
from app.core.config import settings

# (prefix, router)
ROUTERS: list[tuple[str, APIRouter]] = [
    ("", health.router),
    (settings.api_v1_prefix, auth.router),
    (settings.api_v1_prefix, gym.router),
    (settings.api_v1_prefix, branches.router),
    (settings.api_v1_prefix, staff.router),
    (settings.api_v1_prefix, plans.router),
    (settings.api_v1_prefix, payment_methods.router),
    (settings.api_v1_prefix, members.router),
    (settings.api_v1_prefix, memberships.router),
    (settings.api_v1_prefix, payments.router),
    (settings.api_v1_prefix, messaging.router),
    (settings.api_v1_prefix, door.router),
    (settings.api_v1_prefix, payment_requests.router),
    (settings.api_v1_prefix, member_app.router),
    (settings.api_v1_prefix, files.router),
]


def include_all(app: FastAPI) -> None:
    for prefix, router in ROUTERS:
        app.include_router(router, prefix=prefix)
