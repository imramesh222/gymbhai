import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.activity import ActivityLog
from app.models.billing import GymSubscription
from app.models.gym import Branch, Gym
from app.models.staff import StaffUser

SIGNUP = {
    "gym_name": "Fitness Zone",
    "slug": "fitness-zone",
    "branch_name": "Baneshwor",
    "plan_months": "bs",
    "date_display": "both",
    "owner_name": "Sita Sharma",
    "owner_phone": "+977 984-1234567",
    "owner_email": "Sita@Example.com",
    "password": "correct-horse-battery",
}


def test_sign_up_creates_gym_branch_owner_and_trial(
    client: TestClient, db: Session
) -> None:
    response = client.post("/api/v1/auth/register-gym", json=SIGNUP)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["access_token"]
    assert body["me"]["staff"]["is_owner"] is True
    assert body["me"]["gym"]["slug"] == "fitness-zone"
    assert body["me"]["gym"]["settings"]["plan_months"] == "bs"
    assert body["me"]["gym"]["settings"]["date_display"] == "both"
    assert body["me"]["subscription"]["status"] == "trial"
    assert body["me"]["subscription"]["days_left"] == 14
    assert "gb_refresh" in response.cookies

    gym = db.scalars(select(Gym).where(Gym.slug == "fitness-zone")).one()
    assert gym.config.dues_rule == "warn"
    branch = db.scalars(select(Branch).where(Branch.gym_id == gym.id)).one()
    assert branch.name == "Baneshwor"

    owner = db.scalars(select(StaffUser).where(StaffUser.gym_id == gym.id)).one()
    assert owner.phone == "9841234567"
    assert owner.email == "sita@example.com"
    assert owner.password_hash != SIGNUP["password"]

    trial = db.scalars(
        select(GymSubscription).where(GymSubscription.gym_id == gym.id)
    ).one()
    assert trial.starts_on == today_in_nepal()
    assert trial.ends_on == today_in_nepal() + dt.timedelta(days=13)

    logged = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "gym.registered")
    ).one()
    assert logged.gym_id == gym.id
    assert logged.actor_id == owner.id


def test_calendar_choice_is_required(client: TestClient) -> None:
    payload = {k: v for k, v in SIGNUP.items() if k != "plan_months"}
    response = client.post("/api/v1/auth/register-gym", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert {"field": "plan_months", "type": "missing"} in response.json()["fields"]


def test_slug_already_taken(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register-gym", json=SIGNUP).status_code == 201
    again = {**SIGNUP, "owner_phone": "9801111111", "owner_email": "x@example.com"}
    response = client.post("/api/v1/auth/register-gym", json=again)
    assert response.status_code == 409
    assert response.json()["code"] == "slug_taken"


def test_login_already_used_by_another_gyms_staff(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register-gym", json=SIGNUP).status_code == 201
    other = {**SIGNUP, "slug": "iron-house", "owner_email": None}
    response = client.post("/api/v1/auth/register-gym", json=other)
    assert response.status_code == 409
    assert response.json()["code"] == "account_exists"


def test_reserved_slug(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register-gym", json={**SIGNUP, "slug": "staff"}
    )
    assert response.status_code == 422


def test_invalid_phone(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register-gym", json={**SIGNUP, "owner_phone": "01-4412345"}
    )
    assert response.status_code == 422
    assert response.json()["fields"][0]["field"] == "owner_phone"
