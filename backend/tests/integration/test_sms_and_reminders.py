import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.jobs  # noqa: F401  (registers the handlers)
from app import worker
from app.core.time import NEPAL, today_in_nepal
from app.models.messaging import ReminderLog, SmsMessage
from app.services import reminders
from app.services.sms import service as sms
from app.services.sms.providers import SmsError
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()


def messages(db: Session, **where) -> list[SmsMessage]:
    stmt = select(SmsMessage)
    for key, value in where.items():
        stmt = stmt.where(getattr(SmsMessage, key) == value)
    return list(db.scalars(stmt.order_by(SmsMessage.created_at)))


def test_a_new_gym_starts_with_trial_credits_and_rules(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/sms").json()["balance"] == 50
    rules = client.get("/api/v1/reminder-rules").json()
    assert [r["days_from_expiry"] for r in rules] == [-7, -3, 0, 3]


def test_welcome_sms_on_add_and_sale(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    plan = priced_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    client.post(
        "/api/v1/members",
        json={
            "name": "Sita Rai",
            "phone": "9812345678",
            "membership": {"plan_id": str(plan.id)},
        },
    )
    [welcome] = messages(db, kind="welcome")
    assert welcome.to == "9812345678"
    assert welcome.body.startswith("Welcome to Gym fitness-zone, Sita! Active until")
    # Even with dates in AD and BS, the welcome fits one SMS.
    assert welcome.segments == 1
    assert "http://localhost:3000/fitness-zone" in welcome.body
    assert welcome.status == "queued"

    # The worker sends it and charges one credit.
    assert worker.run_once(db) >= 1
    db.refresh(welcome)
    assert welcome.status == "sent"
    assert welcome.provider == "console"
    assert sms.balance(db, gym_a.gym.id) == 49


def test_renewal_sends_active_until(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    plan = priced_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    client.post(
        f"/api/v1/members/{member.id}/memberships", json={"plan_id": str(plan.id)}
    )
    [renewal] = messages(db, kind="membership")
    assert "active until" in renewal.body


def test_no_credit_means_not_sent(db: Session, gym_a: GymFixture) -> None:
    sms.add_credits(db, gym_a.gym.id, -50, "test")
    message = sms.queue(
        db, gym_id=gym_a.gym.id, to="9812345678", body="Hi", kind="manual"
    )
    db.commit()
    worker.run_once(db)
    db.refresh(message)
    assert message.status == "no_credit"
    assert sms.balance(db, gym_a.gym.id) == 0


def test_sign_in_codes_are_never_charged(db: Session, gym_a: GymFixture) -> None:
    sms.add_credits(db, gym_a.gym.id, -50, "test")
    message = SmsMessage(
        gym_id=gym_a.gym.id, to="9812345678", body="123456", kind="otp", segments=1
    )
    db.add(message)
    db.flush()
    assert sms.send_now(db, message)
    assert sms.balance(db, gym_a.gym.id) == 0


def test_a_failing_gateway_is_retried_then_marked_failed(
    db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    class Down:
        name = "down"

        def send(self, to: str, body: str):
            raise SmsError("gateway down")

    monkeypatch.setattr("app.services.sms.service.get_provider", lambda: Down())
    message = sms.queue(
        db, gym_id=gym_a.gym.id, to="9812345678", body="Hi", kind="manual"
    )
    db.commit()
    for _ in range(worker.MAX_ATTEMPTS):
        db.execute(
            worker.Job.__table__.update().values(
                run_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
            )
        )
        db.commit()
        worker.run_once(db)
    db.refresh(message)
    assert message.status == "failed"
    assert "gateway down" in message.error
    assert sms.balance(db, gym_a.gym.id) == 50


# --- reminders -------------------------------------------------------------------


def expiring_in(db: Session, gym: GymFixture, days: int, phone: str):
    member = make_member(db, gym, phone=phone, name=f"Member {phone[-2:]}")
    end = TODAY + dt.timedelta(days=days)
    membership, _ = sell(
        db,
        gym,
        member,
        paid=1500_00,
        start_date=min(TODAY, end) - dt.timedelta(days=20),
        end_date=end,
    )
    return member, membership


def test_reminders_follow_the_rules(db: Session, gym_a: GymFixture) -> None:
    week, _ = expiring_in(db, gym_a, 7, "9800000071")
    today, _ = expiring_in(db, gym_a, 0, "9800000070")
    lapsed, _ = expiring_in(db, gym_a, -3, "9800000073")
    later, _ = expiring_in(db, gym_a, 20, "9800000074")

    assert reminders.run_daily(db) == 3
    db.commit()
    sent = {m.member_id: m.body for m in messages(db, kind="reminder")}
    assert set(sent) == {week.id, today.id, lapsed.id}
    assert "ends today" in sent[today.id]
    assert "We miss you" in sent[lapsed.id]
    assert later.id not in sent

    # Never twice for the same rule and membership.
    assert reminders.run_daily(db) == 0


def test_someone_who_renewed_is_not_reminded(db: Session, gym_a: GymFixture) -> None:
    member, current = expiring_in(db, gym_a, 7, "9800000081")
    sell(db, gym_a, member, start_date=current.end_date + dt.timedelta(days=1))
    assert reminders.run_daily(db) == 0


def test_a_missed_day_is_caught_up_once(db: Session, gym_a: GymFixture) -> None:
    expiring_in(db, gym_a, 6, "9800000091")  # the 7-day reminder was due yesterday
    assert reminders.run_daily(db) == 1
    db.commit()
    [reminder] = messages(db, kind="reminder")
    assert "ends on" in reminder.body
    assert db.scalars(select(ReminderLog)).one()


def test_disabled_rules_do_nothing(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    expiring_in(db, gym_a, 7, "9800000092")
    sign_in(db, client, gym_a.owner)
    for rule in client.get("/api/v1/reminder-rules").json():
        client.patch(f"/api/v1/reminder-rules/{rule['id']}", json={"enabled": False})
    assert reminders.run_daily(db) == 0


def test_daily_tasks_queue_once_a_day_at_their_time(db: Session) -> None:
    morning = dt.datetime.combine(TODAY, dt.time(8, 59), tzinfo=NEPAL)
    assert reminders.JOB_DAILY not in worker.queue_daily(db, morning)
    nine = dt.datetime.combine(TODAY, dt.time(9, 0), tzinfo=NEPAL)
    assert reminders.JOB_DAILY in worker.queue_daily(db, nine)
    assert reminders.JOB_DAILY not in worker.queue_daily(
        db, nine + dt.timedelta(hours=1)
    )


# --- the Expiring list, one-off SMS, notices ---


def test_expiring_lists(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    week, _ = expiring_in(db, gym_a, 5, "9800000101")
    today, _ = expiring_in(db, gym_a, 0, "9800000102")
    lapsed, _ = expiring_in(db, gym_a, -10, "9800000103")
    expiring_in(db, gym_a, -40, "9800000104")
    expiring_in(db, gym_a, 30, "9800000105")
    sign_in(db, client, gym_a.owner)
    lists = client.get("/api/v1/lists/expiring").json()
    assert [m["id"] for m in lists["due_this_week"]] == [str(week.id)]
    assert [m["id"] for m in lists["due_today"]] == [str(today.id)]
    assert [m["id"] for m in lists["lapsed"]] == [str(lapsed.id)]


def test_send_reminder_now(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member, _ = expiring_in(db, gym_a, 3, "9800000111")
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/members/{member.id}/sms", json={"reminder": True})
    assert response.status_code == 201
    assert "3 days left" in response.json()["body"]
    typed = client.post(
        f"/api/v1/members/{member.id}/sms", json={"body": "Your locker key?"}
    )
    assert typed.json()["kind"] == "manual"
    assert client.post(f"/api/v1/members/{member.id}/sms", json={}).status_code == 422


def test_notice_with_sms_shows_the_cost_first(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    expiring_in(db, gym_a, 10, "9800000121")
    expiring_in(db, gym_a, 12, "9800000122")
    expiring_in(db, gym_a, -5, "9800000123")  # lapsed: not sent notices
    sign_in(db, client, gym_a.owner)
    notice = {"title": "Closed Saturday", "body": "For Tihar.", "send_sms": True}
    cost = client.post("/api/v1/notices/cost", json=notice).json()
    assert cost == {
        "recipients": 2,
        "segments_each": 1,
        "total_credits": 2,
        "balance": 50,
    }
    created = client.post("/api/v1/notices", json=notice).json()
    assert created["sms_count"] == 2
    assert len(messages(db, kind="notice")) == 2
    assert client.get("/api/v1/notices").json()[0]["title"] == "Closed Saturday"


def test_sms_templates_are_editable(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        "/api/v1/sms-templates", json={"welcome_sms": "स्वागत छ {name}! {link}"}
    )
    assert response.json()["welcome_sms"] == "स्वागत छ {name}! {link}"
    member = client.post(
        "/api/v1/members", json={"name": "Hari", "phone": "9800000131"}
    )
    assert member.status_code == 201
    [welcome] = messages(db, kind="welcome")
    # Welcome without a membership uses the plain wording.
    assert welcome.body.startswith("Welcome to Gym fitness-zone, Hari!")


@pytest.fixture(autouse=True)
def _console_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "sms_provider", "console")
