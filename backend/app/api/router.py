"""Every router the app serves, and where.

Kept as an explicit list because the regression tests walk it: FastAPI nests
included routers in private wrapper objects, so `app.routes` is not a reliable
way to enumerate endpoints.
"""

from fastapi import APIRouter, FastAPI

from app.api.routes import (
    admin,
    adms,
    auth,
    branches,
    changelog,
    data,
    door,
    expenses,
    files,
    freeze_requests,
    gym,
    health,
    leads,
    live,
    member_app,
    member_socket,
    members,
    memberships,
    messaging,
    payment_methods,
    payment_requests,
    payments,
    plans,
    reader_bridge,
    receipts,
    staff,
    staff_push,
    subscription,
    training,
)
from app.core.config import settings

# (prefix, router)
ROUTERS: list[tuple[str, APIRouter]] = [
    ("", health.router),
    # Readers call these at the root, as ADMS has it (§18.2).
    ("", adms.router),
    (settings.api_v1_prefix, auth.router),
    (settings.api_v1_prefix, staff_push.router),
    (settings.api_v1_prefix, changelog.router),
    (settings.api_v1_prefix, gym.router),
    (settings.api_v1_prefix, branches.router),
    (settings.api_v1_prefix, staff.router),
    (settings.api_v1_prefix, plans.router),
    (settings.api_v1_prefix, payment_methods.router),
    (settings.api_v1_prefix, members.router),
    (settings.api_v1_prefix, leads.router),
    (settings.api_v1_prefix, memberships.router),
    (settings.api_v1_prefix, payments.router),
    (settings.api_v1_prefix, expenses.router),
    (settings.api_v1_prefix, training.router),
    (settings.api_v1_prefix, messaging.router),
    (settings.api_v1_prefix, data.router),
    (settings.api_v1_prefix, door.router),
    (settings.api_v1_prefix, reader_bridge.router),
    (settings.api_v1_prefix, payment_requests.router),
    (settings.api_v1_prefix, freeze_requests.router),
    (settings.api_v1_prefix, member_app.router),
    (settings.api_v1_prefix, member_socket.router),
    (settings.api_v1_prefix, subscription.router),
    (settings.api_v1_prefix, admin.router),
    (settings.api_v1_prefix, files.router),
    (settings.api_v1_prefix, receipts.router),
    (settings.api_v1_prefix, live.router),
]


def include_all(app: FastAPI) -> None:
    for prefix, router in ROUTERS:
        app.include_router(router, prefix=prefix)
