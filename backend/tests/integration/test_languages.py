"""Nepali (PLAN.md §16.6): the gym's language is the default for staff,
members and SMS wording; each account can choose its own."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import sms_defaults
from app.models.gym import Gym
from app.models.messaging import ReminderRule
from app.services import member_auth
from tests.conftest import GymFixture, make_member, sign_in


def test_a_gym_that_signs_up_in_nepali(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/auth/register-gym",
        json={
            "gym_name": "Shakti Gym",
            "slug": "shakti-gym",
            "plan_months": "bs",
            "date_display": "bs",
            "owner_name": "Hari Thapa",
            "owner_phone": "9841800001",
            "password": "correct-horse-battery",
            "accept_terms": True,
            "language": "ne",
        },
    )
    assert response.status_code == 201, response.text
    gym = db.scalars(select(Gym).where(Gym.slug == "shakti-gym")).one()
    assert gym.config.language == "ne"
    assert gym.config.welcome_sms == sms_defaults.WELCOME["ne"]
    templates = db.scalars(
        select(ReminderRule.template).where(ReminderRule.gym_id == gym.id)
    ).all()
    assert all(any("ऀ" <= ch <= "ॿ" for ch in text) for text in templates)
    token = response.json()["access_token"]
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert (me["language"], me["own_language"]) == ("ne", None)


def test_switching_keeps_what_the_gym_wrote(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    client.patch(
        "/api/v1/sms-templates", json={"membership_sms": "Our own words {name}"}
    )
    client.patch(
        "/api/v1/gym", json={"settings": {"language": "ne", "digits": "nepali"}}
    )
    db.refresh(gym_a.gym)
    config = gym_a.gym.config
    assert config.welcome_sms == sms_defaults.WELCOME["ne"]  # never edited: follows
    assert config.membership_sms == "Our own words {name}"  # theirs: stays
    me = client.get("/api/v1/auth/me").json()
    assert (me["language"], me["digits"]) == ("ne", "nepali")

    # Back again: the defaults return to English.
    client.patch("/api/v1/gym", json={"settings": {"language": "en"}})
    db.refresh(gym_a.gym)
    assert gym_a.gym.config.welcome_sms == sms_defaults.WELCOME["en"]


def test_each_account_its_own(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    mine = client.put("/api/v1/auth/me/language", json={"language": "ne"}).json()
    assert (mine["language"], mine["own_language"]) == ("ne", "ne")
    back = client.put("/api/v1/auth/me/language", json={"language": None}).json()
    assert back["language"] == "en"

    member = make_member(db, gym_a)
    issued = member_auth.start_session(db, member, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    assert client.get("/api/v1/m/me").json()["language"] == "en"
    chosen = client.patch("/api/v1/m/me", json={"language": "ne"}).json()
    assert (chosen["language"], chosen["own_language"]) == ("ne", "ne")
