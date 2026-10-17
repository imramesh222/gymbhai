"""Every endpoint checks a specific permission (CLAUDE.md, PLAN.md §2.1, §11).

A new route fails this test until it either declares what it needs with
`require(Permission.X)`, or is added below with the reason it needs none.
"""

from fastapi.dependencies.models import Dependant

from app.api.deps import (
    current_device,
    current_member,
    current_staff,
    require_owner,
    require_platform_admin,
)
from tests.routes import all_routes

# No sign-in at all.
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/health/ready"),
    ("POST", "/api/v1/auth/register-gym"),
    ("POST", "/api/v1/auth/login"),
    # The two-step token from the password step is the proof so far.
    ("POST", "/api/v1/auth/login/two-step"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    # Forgot password: the code sent to the account's email or phone is the proof.
    ("POST", "/api/v1/auth/password-reset"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    # The signed, expiring link is the permission (app/services/storage.py).
    ("GET", "/api/v1/files/{key}"),
    # Likewise a shared receipt (app/core/signed_links.py, §16.3 8.4).
    ("GET", "/api/v1/receipts/{payment_id}.pdf"),
    # The member app before sign-in: gym name and logo, and sign-in codes.
    ("GET", "/api/v1/m/{slug}/gym"),
    ("GET", "/api/v1/m/{slug}/logo"),
    ("POST", "/api/v1/m/{slug}/otp/request"),
    ("POST", "/api/v1/m/{slug}/otp/verify"),
    # The join form, while the gym has it on (§16.4, 9.5).
    ("GET", "/api/v1/m/{slug}/join"),
    ("POST", "/api/v1/m/{slug}/join"),
    ("POST", "/api/v1/m/auth/refresh"),
    ("POST", "/api/v1/m/auth/logout"),
}

# Signed in, but deliberately no permission: every staff member needs these.
ANY_STAFF = {
    # Who am I — also used by platform admins, who have no gym.
    ("GET", "/api/v1/auth/me"),
    # Your own language (§16.6).
    ("PUT", "/api/v1/auth/me/language"),
    # What's new in GymBhai: the same for everyone (§16.5, 10.4).
    ("GET", "/api/v1/changelog"),
    ("POST", "/api/v1/changelog/seen"),
    # Your own password; the current one is required.
    ("POST", "/api/v1/auth/password"),
    # Your own two-step sign-in; the password is required to change it. These
    # stay open to an account that must set it up and hasn't yet.
    ("GET", "/api/v1/auth/two-step"),
    ("POST", "/api/v1/auth/two-step/setup"),
    ("POST", "/api/v1/auth/two-step/enable"),
    ("POST", "/api/v1/auth/two-step/recovery-codes"),
    ("POST", "/api/v1/auth/two-step/disable"),
    # Your own signed-in devices; another account's are not found.
    ("GET", "/api/v1/auth/sessions"),
    ("POST", "/api/v1/auth/sessions/sign-out-others"),
    ("POST", "/api/v1/auth/sessions/{session_id}/sign-out"),
    # Selling needs the plans and their prices.
    ("GET", "/api/v1/plans"),
    # The desk shows members the gym's own payment QR.
    ("GET", "/api/v1/payment-methods"),
    # The gym's name, logo and calendar are needed to render any screen.
    ("GET", "/api/v1/gym"),
    # Staff pick a branch for check-in and sales; the list is branch-filtered.
    ("GET", "/api/v1/branches"),
    ("GET", "/api/v1/branches/{branch_id}"),
    # Live updates: each event is filtered by permission (app/services/live.py).
    ("GET", "/api/v1/live"),
}


# The owner only, whatever permissions are ticked (`require_owner`).
OWNER_ONLY = {
    # Requiring two-step sign-in for every staff account.
    ("PATCH", "/api/v1/gym/security"),
    # Erasing a member: it can't be undone.
    ("POST", "/api/v1/members/{member_id}/erase"),
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
        elif path.startswith("/api/v1/admin/"):
            # Us: every gym. Never reachable with a gym staff account.
            assert require_platform_admin in calls, (
                f"{method} {path} is an admin route without the admin check"
            )
        elif path.startswith("/api/v1/kiosk/"):
            # A door scanner: it can check people in and nothing else (§4.3).
            assert current_device in calls and current_staff not in calls, (
                f"{method} {path} is a kiosk route without a device token"
            )
        elif key in ANY_STAFF:
            assert current_staff in calls, f"{method} {path} does not check sign-in"
        elif key in OWNER_ONLY:
            assert require_owner in calls, f"{method} {path} is not owner-only"
        else:
            assert any(required), (
                f"{method} {path} checks no permission. Use require(Permission.X), "
                "or list it in ANY_STAFF with a reason."
            )


def test_allow_lists_have_no_stale_entries() -> None:
    existing = {(method, path) for method, path, _ in _routes()}
    assert PUBLIC - existing == set()
    assert ANY_STAFF - existing == set()
    assert OWNER_ONLY - existing == set()


def test_the_walk_sees_everything_the_app_serves() -> None:
    """A router included outside app/api/router.py would dodge these checks."""
    from app.main import app

    served = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert served == {(method, path) for method, path, _ in _routes()}
