from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.staff import StaffUser
from tests.conftest import GymFixture, sign_in


def test_owner_can_edit_the_gym_and_the_change_is_logged(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        "/api/v1/gym",
        json={"name": "Fitness Zone Baneshwor", "settings": {"date_display": "ad"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Fitness Zone Baneshwor"
    assert body["settings"]["date_display"] == "ad"
    # Unmentioned settings are kept.
    assert body["settings"]["plan_months"] == "bs"

    entry = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "gym.updated")
    ).one()
    assert entry.actor_id == gym_a.owner.id
    assert entry.changes["name"] == {
        "before": "Gym fitness-zone",
        "after": "Fitness Zone Baneshwor",
    }
    assert entry.changes["settings"]["before"]["date_display"] == "both"
    assert entry.changes["settings"]["after"]["date_display"] == "ad"


def test_a_change_to_nothing_is_not_logged(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    assert (
        client.patch("/api/v1/gym", json={"name": "Gym fitness-zone"}).status_code
        == 200
    )
    assert not db.scalars(
        select(ActivityLog).where(ActivityLog.action == "gym.updated")
    ).first()


def test_null_never_clears_a_required_choice(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch("/api/v1/gym", json={"settings": {"plan_months": None}})
    assert response.status_code == 200
    assert response.json()["settings"]["plan_months"] == "bs"
    assert client.patch("/api/v1/gym", json={"name": None}).status_code == 422


def test_staff_without_the_permission_are_refused(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    staff = make_staff(gym_a.gym, permissions=["members.view"])
    sign_in(db, client, staff)
    response = client.patch("/api/v1/gym", json={"name": "Taken over"})
    assert response.status_code == 403
    assert response.json() == {
        "detail": "You don't have permission to do this.",
        "code": "permission_denied",
        "permission": "setup.gym",
    }


def test_permission_changes_take_effect_on_the_next_request(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
) -> None:
    staff = make_staff(gym_a.gym, permissions=["setup.gym"])
    sign_in(db, client, staff)
    assert client.patch("/api/v1/gym", json={"address": "Baneshwor"}).status_code == 200

    staff.permissions = []
    db.commit()
    # Same token, no sign-in in between.
    assert client.patch("/api/v1/gym", json={"address": "Koteshwor"}).status_code == 403


def test_the_daily_summary_can_be_turned_on(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/gym").json()["settings"]["daily_summary_sms"] is False
    response = client.patch(
        "/api/v1/gym", json={"settings": {"daily_summary_sms": True}}
    )
    assert response.json()["settings"]["daily_summary_sms"] is True
