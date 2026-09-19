import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.billing import PlatformPlan
from app.models.messaging import SmsMessage
from app.services import member_auth, owner_messages, subscription
from tests.conftest import GymFixture, lapse, make_member, sell, sign_in

TODAY = today_in_nepal()


def test_a_new_gym_is_on_trial(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    me = client.get("/api/v1/auth/me").json()["subscription"]
    assert me["status"] == "trial" and me["days_left"] == 14 and me["phase"] == "ok"


def test_the_last_week_and_grace(db: Session, gym_a: GymFixture) -> None:
    row = subscription.latest(db, gym_a.gym.id)
    assert (
        subscription.phase_of(row.ends_on, row.ends_on - dt.timedelta(days=3))
        == "ending"
    )
    assert (
        subscription.phase_of(row.ends_on, row.ends_on + dt.timedelta(days=7))
        == "grace"
    )
    assert (
        subscription.phase_of(row.ends_on, row.ends_on + dt.timedelta(days=8))
        == "read_only"
    )


def test_lapsed_gyms_are_read_only(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    lapse(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)

    assert client.get("/api/v1/members").status_code == 200
    assert client.get("/api/v1/export/members.xlsx").status_code == 200
    blocked = client.post(
        "/api/v1/members", json={"name": "New", "phone": "9800000123"}
    )
    assert blocked.status_code == 402
    assert blocked.json()["code"] == "subscription_lapsed"
    assert (
        client.patch(f"/api/v1/members/{member.id}", json={"name": "X"}).status_code
        == 402
    )
    assert client.get("/api/v1/auth/me").json()["subscription"]["phase"] == "read_only"


def test_members_and_the_door_keep_working(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """Members are never punished for the owner's unpaid bill (§5.7)."""
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    lapse(db, gym_a.gym)
    issued = member_auth.start_session(db, member, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    assert client.get("/api/v1/m/me").json()["state"]["status"] == "active"


def test_a_lapsed_gym_can_still_pay(
    client: TestClient, db: Session, gym_a: GymFixture, platform_admin
) -> None:
    plan = PlatformPlan(name="Standard", monthly_price=2000_00, included_sms=100)
    db.add(plan)
    db.commit()
    lapse(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)

    overview = client.get("/api/v1/subscription").json()
    assert overview["phase"] == "read_only"
    assert [p["name"] for p in overview["plans"]] == ["Standard"]
    sent = client.post(
        "/api/v1/subscription/payments",
        json={"platform_plan_id": str(plan.id), "months": 3, "amount": 6000_00,
              "transaction_ref": "ES-GYM-1"},
    )  # fmt: skip
    assert sent.status_code == 201, sent.text

    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    [pending] = admin.get("/api/v1/admin/subscription-payments").json()
    assert pending["gym_name"] == "Gym fitness-zone"
    approved = admin.post(
        f"/api/v1/admin/subscription-payments/{pending['id']}/approve", json={}
    )
    assert approved.json()["status"] == "approved"

    state = subscription.state(db, gym_a.gym.id)
    assert state.phase == "ok" and state.plan_name == "Standard"
    assert state.ends_on > TODAY + dt.timedelta(days=80)
    # Out of read-only, with the plan's SMS added.
    assert (
        client.post(
            "/api/v1/members", json={"name": "N", "phone": "9800000124"}
        ).status_code
        == 201
    )
    assert client.get("/api/v1/subscription").json()["sms_balance"] == 50 + 300
    told = db.scalars(select(SmsMessage).where(SmsMessage.kind == "platform")).one()
    assert "active until" in told.body


def test_reminders_7_and_2_days_before(db: Session, gym_a: GymFixture) -> None:
    row = subscription.latest(db, gym_a.gym.id)
    assert (
        owner_messages.subscription_reminders(db, row.ends_on - dt.timedelta(days=6))
        == 1
    )
    assert (
        owner_messages.subscription_reminders(db, row.ends_on - dt.timedelta(days=5))
        == 0
    )
    assert (
        owner_messages.subscription_reminders(db, row.ends_on - dt.timedelta(days=1))
        == 1
    )
    db.commit()
    texts = [
        m.body
        for m in db.scalars(select(SmsMessage).where(SmsMessage.kind == "platform"))
    ]
    assert "(7 days)" in texts[0] and "(2 days)" in texts[1]


def test_reminders_to_the_owner_cost_the_gym_nothing(
    db: Session, gym_a: GymFixture
) -> None:
    from app import worker
    from app.services.sms import service as sms

    row = subscription.latest(db, gym_a.gym.id)
    owner_messages.subscription_reminders(db, row.ends_on - dt.timedelta(days=6))
    db.commit()
    worker.run_once(db)
    assert sms.balance(db, gym_a.gym.id) == 50


def test_daily_summary_only_when_turned_on(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    assert owner_messages.daily_summaries(db) == 0
    gym_a.gym.settings = {**gym_a.gym.settings, "daily_summary_sms": True}
    db.commit()
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    assert owner_messages.daily_summaries(db) == 1
    db.commit()
    summary = db.scalars(select(SmsMessage).where(SmsMessage.kind == "summary")).one()
    assert "Rs 1,500 collected" in summary.body
