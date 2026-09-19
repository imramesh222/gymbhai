"""Every endpoint the app serves, as (method, full path, route)."""

import re

from fastapi.routing import APIRoute

from app.api.router import ROUTERS

# "{key:path}" in a route is "{key}" in the OpenAPI schema.
_CONVERTER = re.compile(r"\{(\w+):\w+\}")


def all_routes() -> list[tuple[str, str, APIRoute]]:
    rows = []
    for prefix, router in ROUTERS:
        for route in router.routes:
            assert isinstance(route, APIRoute), f"unexpected route {route!r}"
            path = _CONVERTER.sub(r"{\1}", prefix + route.path)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                rows.append((method, path, route))
    assert rows, "found no routes at all; the walk is broken"
    return rows
