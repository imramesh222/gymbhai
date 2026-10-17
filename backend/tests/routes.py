"""Every endpoint the app serves, as (method, full path, route)."""

import re

from fastapi.routing import APIRoute, APIWebSocketRoute

from app.api.router import ROUTERS

# WebSockets sign in with their first message, not a dependency, so the
# permission walk can't see how. Each is listed here with the tests that prove
# it turns strangers away; a new one fails the walk until it is added.
WEBSOCKETS = {
    # The phone app (PLAN.md §17.3): tests/integration/test_member_socket.py.
    "/api/v1/m/ws",
}

# "{key:path}" in a route is "{key}" in the OpenAPI schema.
_CONVERTER = re.compile(r"\{(\w+):\w+\}")


def all_routes() -> list[tuple[str, str, APIRoute]]:
    rows = []
    for prefix, router in ROUTERS:
        for route in router.routes:
            if isinstance(route, APIWebSocketRoute):
                assert prefix + route.path in WEBSOCKETS, f"unlisted socket {route!r}"
                continue
            assert isinstance(route, APIRoute), f"unexpected route {route!r}"
            path = _CONVERTER.sub(r"{\1}", prefix + route.path)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                rows.append((method, path, route))
    assert rows, "found no routes at all; the walk is broken"
    return rows
