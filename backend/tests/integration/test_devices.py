"""Signed-in devices (PLAN.md §16.1, step 6.4)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.staff import StaffSession, StaffUser
from app.services import sessions
from tests.conftest import GymFixture, sign_in


def other_device(db: Session, staff: StaffUser) -> StaffSession:
    issued = sessions.start(db, staff, None)
    db.commit()
    return issued.session


def live_ids(db: Session, staff: StaffUser) -> set:
    return {
        row.id
        for row in db.scalars(
            select(StaffSession).where(
                StaffSession.staff_user_id == staff.id,
                StaffSession.revoked_at.is_(None),
            )
        )
    }


def test_your_devices_with_this_one_marked(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    phone = other_device(db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    rows = client.get("/api/v1/auth/sessions").json()
    assert len(rows) == 2
    assert [r["current"] for r in rows].count(True) == 1
    assert str(phone.id) in {r["id"] for r in rows if not r["current"]}


def test_signing_out_one_other_device(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    phone = other_device(db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/auth/sessions/{phone.id}/sign-out")
    assert response.status_code == 204
    assert phone.id not in live_ids(db, gym_a.owner)
    assert len(client.get("/api/v1/auth/sessions").json()) == 1


def test_this_device_signs_out_with_sign_out(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    current = client.get("/api/v1/auth/sessions").json()[0]["id"]
    response = client.post(f"/api/v1/auth/sessions/{current}/sign-out")
    assert response.status_code == 409
    assert response.json()["code"] == "current_session"


def test_signing_out_every_other_device(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    other_device(db, gym_a.owner)
    other_device(db, gym_a.owner)
    sign_in(db, client, gym_a.owner)
    response = client.post("/api/v1/auth/sessions/sign-out-others")
    assert response.json() == {"signed_out": 2}
    # This device still works.
    assert client.get("/api/v1/auth/me").status_code == 200
    assert len(live_ids(db, gym_a.owner)) == 1


def test_a_colleagues_device_is_not_found(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    desk = make_staff(gym_a.gym)
    theirs = other_device(db, desk)
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/auth/sessions/{theirs.id}/sign-out")
    assert response.status_code == 404
    assert theirs.id in live_ids(db, desk)


def test_the_owner_signs_a_colleague_out_everywhere(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    desk = make_staff(gym_a.gym)
    other_device(db, desk)
    other_device(db, desk)
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/staff/{desk.id}/sign-out")
    assert response.json() == {"signed_out": 2}
    assert live_ids(db, desk) == set()


def test_nobody_signs_out_the_owner_or_themselves_from_staff(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    manager = make_staff(gym_a.gym, permissions=["staff.manage"])
    sign_in(db, client, manager)
    own = client.post(f"/api/v1/staff/{manager.id}/sign-out")
    assert own.status_code == 409
    owner = client.post(f"/api/v1/staff/{gym_a.owner.id}/sign-out")
    assert owner.status_code == 403


def test_a_signed_out_device_stops_at_once(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """Revoked means the next request, not when the access token runs out."""
    token = sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/auth/me").status_code == 200
    second = TestClient(client.app)
    sign_in(db, second, gym_a.owner)
    second.post("/api/v1/auth/sessions/sign-out-others")
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "session_ended"
