"""Messages the desk sends on WhatsApp from its own phone (PLAN.md §18.5).

The server only fills in the gym's own wording; nothing is sent from here.
"""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.messaging import SmsMessage
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()
LINK = "http://localhost:3000/fitness-zone"


def message(client: TestClient, member_id, purpose: str | None = None):
    params = {"purpose": purpose} if purpose else {}
    return client.get(f"/api/v1/members/{member_id}/message", params=params)


def test_a_renewal_reminder_in_the_gyms_wording(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00, start_date=TODAY - dt.timedelta(days=26),
         end_date=TODAY + dt.timedelta(days=3))  # fmt: skip
    sign_in(db, client, gym_a.owner)
    # The reminder is what Follow up's "Remind" sends: the nearest expiry rule.
    body = message(client, member.id).json()
    assert body == {
        "text": f"Hi Sita, 3 days left on your Gym fitness-zone membership. "
        f"Renew: {LINK}",
        "phone": "9812345678",
    }
    # Nothing was sent, by SMS or any other way.
    assert db.scalar(select(func.count()).select_from(SmsMessage)) == 0


def test_money_owed_and_not_visiting(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=500_00)
    sign_in(db, client, gym_a.owner)
    dues = message(client, member.id, "dues").json()["text"]
    assert "Rs 1,000 is still to pay" in dues
    away = message(client, member.id, "not_visiting").json()["text"]
    assert away.startswith("Hi Sita, we've missed you at Gym fitness-zone!")
    assert "It's been 0 days" in away


def test_the_welcome_carries_the_apps_link(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    text = message(client, member.id, "welcome").json()["text"]
    assert text == f"Welcome to Gym fitness-zone, Sita! Your app: {LINK}"


def test_the_gyms_own_edited_wording_is_used(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=0)
    sign_in(db, client, gym_a.owner)
    rules = client.get("/api/v1/reminder-rules").json()
    dues_rule = next(r for r in rules if r["trigger"] == "dues")
    client.patch(
        f"/api/v1/reminder-rules/{dues_rule['id']}",
        json={"template": "Namaste {name}, Rs {amount} baki chha."},
    )
    text = message(client, member.id, "dues").json()["text"]
    assert text == "Namaste Sita, Rs 1,500 baki chha."


def test_seeing_the_member_is_enough(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    """It's a call in writing, from the desk's phone: no SMS permission."""
    member = make_member(db, gym_a)
    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert message(client, member.id).status_code == 200
    sign_in(db, client, make_staff(gym_a.gym, permissions=["payments.collect"]))
    refused = message(client, member.id)
    assert refused.json()["permission"] == "members.view"


def test_not_for_an_erased_member_or_an_unknown_purpose(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    assert message(client, member.id, "gossip").status_code == 422
    client.post(f"/api/v1/members/{member.id}/erase")
    erased = message(client, member.id)
    assert (erased.status_code, erased.json()["code"]) == (409, "member_erased")
