import datetime as dt
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.staff import StaffSession, StaffUser
from app.services import sessions
from tests.conftest import TEST_PASSWORD, GymFixture, sign_in


def login(client: TestClient, identifier: str, password: str = TEST_PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


@pytest.mark.parametrize(
    "identifier", ["a@example.com", "A@Example.COM", "9841000001", "+977-984-1000001"]
)
def test_sign_in_by_email_or_phone(
    client: TestClient, gym_a: GymFixture, identifier: str
) -> None:
    response = login(client, identifier)
    assert response.status_code == 200, response.text
    assert response.json()["me"]["staff"]["id"] == str(gym_a.owner.id)
    assert "gb_refresh" in response.cookies


def test_wrong_password_and_unknown_account_look_the_same(
    client: TestClient, gym_a: GymFixture
) -> None:
    wrong = login(client, "a@example.com", "not-the-password")
    unknown = login(client, "nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_disabled_account_cannot_sign_in(
    client: TestClient, gym_a: GymFixture, make_staff: Callable[..., StaffUser]
) -> None:
    staff = make_staff(gym_a.gym, is_active=False)
    response = login(client, staff.phone)
    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_me(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    body = client.get("/api/v1/auth/me").json()
    assert body["gym"]["id"] == str(gym_a.gym.id)
    assert "staff.manage" in body["permissions"]
    assert body["branch_ids"] is None


def test_refresh_rotates_the_token(client: TestClient, gym_a: GymFixture) -> None:
    first = login(client, "a@example.com").cookies["gb_refresh"]

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    second = refreshed.cookies["gb_refresh"]
    assert second != first
    assert refreshed.json()["access_token"]


def test_old_refresh_token_is_dead_after_the_grace_window(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    old = login(client, "a@example.com").cookies["gb_refresh"]
    assert client.post("/api/v1/auth/refresh").status_code == 200

    # Two tabs refreshing together: the old token still works, briefly...
    client.cookies.set("gb_refresh", old, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 200

    # ...but not once the grace window has passed.
    session = db.query(StaffSession).one()
    session.rotated_at -= sessions.ROTATION_GRACE + dt.timedelta(seconds=1)
    db.commit()
    client.cookies.set("gb_refresh", old, path="/api/v1/auth")
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == "session_ended"


def test_refresh_without_a_cookie(client: TestClient) -> None:
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_ends_the_session_and_its_access_token(
    client: TestClient, gym_a: GymFixture
) -> None:
    signed_in = login(client, "a@example.com")
    client.headers["Authorization"] = f"Bearer {signed_in.json()['access_token']}"
    assert client.get("/api/v1/auth/me").status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(
        "gb_refresh", signed_in.cookies["gb_refresh"], path="/api/v1/auth"
    )
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_disabling_an_account_takes_effect_immediately(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    """PLAN.md §2.1: not at next sign-in, and not when the token expires."""
    staff = make_staff(gym_a.gym, permissions=["setup.gym"])
    sign_in(db, client, staff)
    assert client.get("/api/v1/gym").status_code == 200

    staff.is_active = False
    db.commit()

    response = client.get("/api/v1/gym")
    assert response.status_code == 401
    assert response.json()["code"] == "session_ended"


def test_expired_session_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    session = db.query(StaffSession).one()
    session.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_platform_admin_has_no_gym(client: TestClient, db: Session) -> None:
    admin = StaffUser(
        name="Us",
        email="admin@gymbhai.com",
        password_hash="x",
        is_platform_admin=True,
    )
    db.add(admin)
    db.commit()
    sign_in(db, client, admin)

    me = client.get("/api/v1/auth/me").json()
    assert me["gym"] is None and me["permissions"] == []

    response = client.get("/api/v1/gym")
    assert response.status_code == 403
    assert response.json()["code"] == "no_gym"
