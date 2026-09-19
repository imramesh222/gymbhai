"""Every endpoint checks a specific permission (CLAUDE.md, PLAN.md §2.1, §11).

A new route fails this test until it either declares what it needs with
`require(Permission.X)`, or is added below with the reason it needs none.
"""

from fastapi.dependencies.models import Dependant

from app.api.deps import current_device, current_member, current_staff
from tests.routes import all_routes

# No sign-in at all.
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/health/ready"),
    ("POST", "/api/v1/auth/register-gym"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    # The signed, expiring link is the permission (app/services/storage.py).
    ("GET", "/api/v1/files/{key}"),
    # The member app before sign-in: gym name and logo, and sign-in codes.
    ("GET", "/api/v1/m/{slug}/gym"),
    ("GET", "/api/v1/m/{slug}/logo"),
    ("POST", "/api/v1/m/{slug}/otp/request"),
    ("POST", "/api/v1/m/{slug}/otp/verify"),
    ("POST", "/api/v1/m/auth/refresh"),
    ("POST", "/api/v1/m/auth/logout"),
}

# Signed in, but deliberately no permission: every staff member needs these.
ANY_STAFF = {
    # Who am I — also used by platform admins, who have no gym.
    ("GET", "/api/v1/auth/me"),
    # Your own password; the current one is required.
    ("POST", "/api/v1/auth/password"),
    # Selling needs the plans and their prices.
    ("GET", "/api/v1/plans"),
    # The desk shows members the gym's own payment QR.
    ("GET", "/api/v1/payment-methods"),
    # The gym's name, logo and calendar are needed to render any screen.
    ("GET", "/api/v1/gym"),
    # Staff pick a branch for check-in and sales; the list is branch-filtered.
    ("GET", "/api/v1/branches"),
    ("GET", "/api/v1/branches/{branch_id}"),
}


def _calls(dependant: Dependant) -> list:
    found = [dependant.call]
    for sub in dependant.dependencies:
        found.extend(_calls(sub))
    return found


def _routes() -> list[tuple[str, str, list]]:
    return [(m, path, _calls(route.dependant)) for m, path, route in all_routes()]


def test_every_route_is_accounted_for() -> None:
    for method, path, calls in _routes():
        key = (method, path)
        required = [
            c.required_permissions for c in calls if hasattr(c, "required_permissions")
        ]
        if key in PUBLIC:
            assert not required and current_staff not in calls, (
                f"{method} {path} is listed as public but checks sign-in"
            )
        elif path.startswith("/api/v1/m/"):
            # The member app: signed in as a member, never as staff.
            assert current_member in calls and current_staff not in calls, (
                f"{method} {path} is a member route without member sign-in"
            )
        elif path.startswith("/api/v1/kiosk/"):
            # A door scanner: it can check people in and nothing else (§4.3).
            assert current_device in calls and current_staff not in calls, (
                f"{method} {path} is a kiosk route without a device token"
            )
        elif key in ANY_STAFF:
            assert current_staff in calls, f"{method} {path} does not check sign-in"
        else:
            assert any(required), (
                f"{method} {path} checks no permission. Use require(Permission.X), "
                "or list it in ANY_STAFF with a reason."
            )


def test_allow_lists_have_no_stale_entries() -> None:
    existing = {(method, path) for method, path, _ in _routes()}
    assert PUBLIC - existing == set()
    assert ANY_STAFF - existing == set()


def test_the_walk_sees_everything_the_app_serves() -> None:
    """A router included outside app/api/router.py would dodge these checks."""
    from app.main import app

    served = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert served == {(method, path) for method, path, _ in _routes()}
