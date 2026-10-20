"""WhatsApp messages between push and SMS (PLAN.md §19.3)."""

import datetime as dt
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.jobs  # noqa: F401  (registers the handlers)
from app import worker
from app.core.config import settings
from app.core.time import today_in_nepal, utcnow
from app.core.whatsapp_templates import WhatsApp
from app.models.activity import ActivityLog
from app.models.messaging import (
    CHANNEL_SMS,
    CHANNEL_WHATSAPP,
    ReminderRule,
    SmsCreditLedger,
    SmsMessage,
)
from app.services import members as members_service
from app.services import reminders
from app.services.push import service as push
from app.services.push.providers import PushGone
from app.services.sms import service as sms
from app.services.whatsapp import service as whatsapp
from app.services.whatsapp.providers import (
    NotOnWhatsApp,
    Sent,
    WhatsAppError,
    WhatsAppRejected,
)
from tests.conftest import (
    GymFixture,
    context_for,
    make_gym,
    make_member,
    sell,
    sign_in,
)
from tests.regression.test_member_isolation import member_client

TODAY = today_in_nepal()
SECRET = "meta-app-secret-for-tests"


class FakeWhatsApp:
    """Takes every message, or fails each with `error`."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list = []
        self.texts: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def send_template(self, message) -> Sent:
        if self.error:
            raise self.error
        self.sent.append(message)
        return Sent(provider_ref=f"wamid.{len(self.sent)}")

    def send_text(self, to: str, body: str) -> Sent:
        self.texts.append((to, body))
        return Sent(provider_ref=f"wamid.text.{len(self.texts)}")


class FakePush:
    name = "fake"

    def __init__(self) -> None:
        self.error: Exception | None = None

    def send(self, target, message) -> None:
        if self.error:
            raise self.error


@pytest.fixture
def meta(monkeypatch) -> FakeWhatsApp:
    fake = FakeWhatsApp()
    monkeypatch.setattr(whatsapp, "get_provider", lambda: fake)
    return fake


@pytest.fixture
def phones(monkeypatch) -> FakePush:
    fake = FakePush()
    monkeypatch.setattr(push, "get_provider", lambda target=None: fake)
    return fake


@pytest.fixture
def gym(db: Session, gym_a: GymFixture) -> GymFixture:
    """Gym A with WhatsApp turned on."""
    gym_a.gym.settings = {**gym_a.gym.settings, "whatsapp": True}
    db.commit()
    return gym_a


def agreed(db: Session, fixture: GymFixture, phone: str, name: str = "Sita Rai"):
    member = make_member(db, fixture, name=name, phone=phone)
    member.whatsapp_agreed = True
    db.commit()
    return member


def run_jobs(db: Session) -> None:
    while worker.run_once(db):
        pass


def messages(db: Session, member) -> list[SmsMessage]:
    """WhatsApp first, then SMS: in these tests an SMS only ever follows a
    WhatsApp message, and rows in one test transaction tie on created_at."""
    return list(
        db.scalars(
            select(SmsMessage)
            .where(SmsMessage.member_id == member.id)
            .order_by(SmsMessage.channel.desc(), SmsMessage.created_at)
        )
    )


def tell(db: Session, fixture: GymFixture, member) -> str | None:
    channel, _ = push.notify(
        db,
        fixture.gym,
        member,
        title=fixture.gym.name,
        body="Your membership is active",
        url=f"/{fixture.gym.slug}",
        sms_body="SMS: active until 5 Kartik",
        sms_kind="membership",
        whatsapp=WhatsApp(
            "membership_active",
            {
                "name": "Sita",
                "gym": fixture.gym.name,
                "plan": "1 month",
                "end_date": "5 Kartik",
            },
            button=fixture.gym.slug,
        ),  # fmt: skip
    )
    db.commit()
    return channel


def test_push_then_whatsapp_then_sms(
    db: Session, gym: GymFixture, meta: FakeWhatsApp, phones: FakePush
) -> None:
    with_app = agreed(db, gym, "9800000501", "Ram Thapa")
    push.subscribe_app(
        db, with_app, expo_token="ExponentPushToken[abc]", user_agent="Phone"
    )
    on_whatsapp = agreed(db, gym, "9800000502")
    not_agreed = make_member(db, gym, phone="9800000503")

    assert tell(db, gym, with_app) == "push"
    assert tell(db, gym, on_whatsapp) == "whatsapp"
    assert tell(db, gym, not_agreed) == "sms"
    before = sms.balance(db, gym.gym.id)
    run_jobs(db)

    assert [m.channel for m in messages(db, with_app)] == []
    (sent,) = meta.sent
    assert sent.to == "9800000502"
    assert sent.template == "gymbhai_membership_active"
    assert sent.language == "en"
    assert sent.values == ["Sita", gym.gym.name, "1 month", "5 Kartik"]
    assert sent.button == gym.gym.slug
    (row,) = messages(db, on_whatsapp)
    assert row.channel == CHANNEL_WHATSAPP and row.status == "sent"
    assert row.provider_ref == "wamid.1"
    assert row.body.startswith("Hi Sita, this is")
    assert row.fallback == "SMS: active until 5 Kartik"
    (text,) = messages(db, not_agreed)
    assert text.channel == CHANNEL_SMS and text.body == "SMS: active until 5 Kartik"
    # One credit each, the WhatsApp message's from platform_settings.
    assert sms.balance(db, gym.gym.id) == before - 2
    reasons = set(db.scalars(select(SmsCreditLedger.reason)))
    assert "whatsapp:membership" in reasons


def test_off_until_the_gym_turns_it_on(
    db: Session, gym_a: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym_a, "9800000511")
    assert tell(db, gym_a, member) == "sms"
    gym_a.gym.settings = {**gym_a.gym.settings, "whatsapp": True}
    db.commit()
    assert tell(db, gym_a, member) == "whatsapp"


def test_not_on_whatsapp_sends_the_sms_and_waits_30_days(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000521")
    sister = agreed(db, gym, "9800000521", "Gita Rai")  # the same phone
    meta.error = NotOnWhatsApp("Meta refused (131026)")
    before = sms.balance(db, gym.gym.id)
    tell(db, gym, member)
    run_jobs(db)

    failed, instead = messages(db, member)
    assert failed.channel == CHANNEL_WHATSAPP and failed.status == "failed"
    assert "131026" in failed.error
    assert instead.channel == CHANNEL_SMS and instead.status == "sent"
    assert instead.body == "SMS: active until 5 Kartik"
    # Only the SMS cost anything.
    assert sms.balance(db, gym.gym.id) == before - 1
    db.refresh(member)
    db.refresh(sister)
    assert member.whatsapp_unreachable_at and sister.whatsapp_unreachable_at
    meta.error = None
    assert tell(db, gym, member) == "sms"
    member.whatsapp_unreachable_at = utcnow() - dt.timedelta(days=31)
    db.commit()
    assert tell(db, gym, member) == "whatsapp"
    # A new number is tried at once.
    sister_ctx = context_for(db, gym.owner)
    members_service.update(db, sister_ctx, sister, {"phone": "9800000529"})
    db.commit()
    assert sister.whatsapp_unreachable_at is None


def test_a_refused_message_goes_by_sms_at_once(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000531")
    meta.error = WhatsAppRejected("Meta refused (132001): no such template")
    tell(db, gym, member)
    run_jobs(db)
    assert [(m.channel, m.status) for m in messages(db, member)] == [
        (CHANNEL_WHATSAPP, "failed"),
        (CHANNEL_SMS, "sent"),
    ]
    assert member.whatsapp_unreachable_at is None


def test_meta_down_is_retried_then_the_sms_goes(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000541")
    meta.error = WhatsAppError("Meta refused (131000)")
    tell(db, gym, member)
    for _ in range(worker.MAX_ATTEMPTS):
        run_jobs(db)
        db.execute(
            worker.Job.__table__.update().values(run_at=utcnow() - dt.timedelta(1))
        )
        db.commit()
    run_jobs(db)
    assert [(m.channel, m.status) for m in messages(db, member)] == [
        (CHANNEL_WHATSAPP, "failed"),
        (CHANNEL_SMS, "sent"),
    ]


def test_no_credit_sends_nothing(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000551")
    sms.add_credits(db, gym.gym.id, -sms.balance(db, gym.gym.id), "test")
    db.commit()
    tell(db, gym, member)
    run_jobs(db)
    (row,) = messages(db, member)
    assert row.status == "no_credit" and meta.sent == []


def test_a_push_nobody_takes_goes_by_whatsapp(
    db: Session, gym: GymFixture, meta: FakeWhatsApp, phones: FakePush
) -> None:
    member = agreed(db, gym, "9800000561")
    push.subscribe_app(
        db, member, expo_token="ExponentPushToken[gone]", user_agent="Phone"
    )
    phones.error = PushGone("gone")
    assert tell(db, gym, member) == "push"
    run_jobs(db)
    (row,) = messages(db, member)
    assert row.channel == CHANNEL_WHATSAPP and row.status == "sent"
    assert row.template == "gymbhai_membership_active"


def test_credits_per_message_come_from_admin(
    client: TestClient, db: Session, gym: GymFixture, platform_admin, meta
) -> None:
    sign_in(db, client, platform_admin)
    assert client.get("/api/v1/admin/settings").json() == {
        "whatsapp_credits": 1,
        "whatsapp_available": True,
        # A gym's own app (§20.3): not offered until both are set.
        "branded_app_setup_price": None,
        "branded_app_monthly_price": None,
    }
    response = client.patch("/api/v1/admin/settings", json={"whatsapp_credits": 2})
    assert response.json()["whatsapp_credits"] == 2
    assert client.patch(
        "/api/v1/admin/settings", json={"whatsapp_credits": 0}
    ).status_code == 422  # fmt: skip
    assert db.scalar(
        select(func.count()).where(
            ActivityLog.action == "platform_settings.updated"
        )
    ) == 1  # fmt: skip
    member = agreed(db, gym, "9800000571")
    before = sms.balance(db, gym.gym.id)
    tell(db, gym, member)
    run_jobs(db)
    assert messages(db, member)[0].segments == 2
    assert sms.balance(db, gym.gym.id) == before - 2


# --- automations ---------------------------------------------------------------------


def test_expiry_reminders_go_by_whatsapp_and_win_back_does_not(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    ending = agreed(db, gym, "9800000581", "Hari Gurung")
    sell(db, gym, ending, paid=1500_00, start_date=TODAY - dt.timedelta(days=20),
         end_date=TODAY + dt.timedelta(days=7))  # fmt: skip
    lapsed = agreed(db, gym, "9800000582", "Maya Gurung")
    sell(db, gym, lapsed, paid=1500_00, start_date=TODAY - dt.timedelta(days=60),
         end_date=TODAY - dt.timedelta(days=30))  # fmt: skip
    db.execute(
        ReminderRule.__table__.update()
        .where(ReminderRule.gym_id == gym.gym.id, ReminderRule.trigger == "lapsed")
        .values(enabled=True)
    )
    db.commit()

    reminders.run_daily(db, TODAY)
    db.commit()
    run_jobs(db)

    (week_before,) = messages(db, ending)
    assert week_before.channel == CHANNEL_WHATSAPP
    assert week_before.template == "gymbhai_membership_ends"
    (sent,) = meta.sent
    assert sent.values[0] == "Hari" and sent.button == f"{gym.gym.slug}/renew"
    # Win-back is a marketing message in Meta's terms: SMS, not WhatsApp.
    (win_back,) = messages(db, lapsed)
    assert win_back.channel == CHANNEL_SMS


def test_the_welcome_goes_by_whatsapp_for_those_who_agree(
    client: TestClient, db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    sign_in(db, client, gym.owner)
    response = client.post(
        "/api/v1/members",
        json={"name": "Bina Shrestha", "phone": "9800000591", "whatsapp_agreed": True},
    )
    assert response.status_code == 201
    created = response.json()["member"]
    assert created["whatsapp_agreed"] is True
    rows = list(db.scalars(select(SmsMessage).where(SmsMessage.to == "9800000591")))
    assert [(r.channel, r.kind, r.template) for r in rows] == [
        (CHANNEL_WHATSAPP, "welcome", "gymbhai_welcome_no_plan")
    ]

    # Unticked at the desk: logged, and the welcome goes by SMS.
    off = client.patch(
        f"/api/v1/members/{created['id']}", json={"whatsapp_agreed": False}
    )
    assert off.json()["whatsapp_agreed"] is False
    entry = db.scalars(
        select(ActivityLog).where(
            ActivityLog.entity_id == created["id"],
            ActivityLog.action == "member.updated",
        )
    ).one()
    assert entry.changes == {"whatsapp_agreed": {"before": True, "after": False}}
    client.post(f"/api/v1/members/{created['id']}/resend-welcome")
    # (Rows written in one test transaction share a created_at: no "latest".)
    channels = db.scalars(
        select(SmsMessage.channel).where(SmsMessage.to == "9800000591")
    ).all()
    assert sorted(channels) == [CHANNEL_SMS, CHANNEL_WHATSAPP]
    assert client.patch(
        f"/api/v1/members/{created['id']}", json={"whatsapp_agreed": None}
    ).status_code == 422  # fmt: skip


def test_members_choose_in_their_app(
    client: TestClient, db: Session, gym: GymFixture
) -> None:
    member = make_member(db, gym, phone="9800000601")
    member_client(db, client, member)
    me = client.get("/api/v1/m/me").json()
    assert me["whatsapp"] is True and me["whatsapp_agreed"] is False
    me = client.patch("/api/v1/m/me", json={"whatsapp_agreed": True}).json()
    assert me["whatsapp_agreed"] is True
    assert member.whatsapp_agreed_at is not None
    action = db.scalars(
        select(ActivityLog.action).where(ActivityLog.actor_id == member.id)
    ).all()
    assert "member.updated_own" in action
    # A gym without WhatsApp: the app shows no switch.
    gym.gym.settings = {**gym.gym.settings, "whatsapp": False}
    db.commit()
    assert client.get("/api/v1/m/me").json()["whatsapp"] is False


def test_turning_it_on_needs_whatsapp_set_up(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    sign_in(db, client, gym_a.owner)
    body = {"settings": {"whatsapp": True}}
    monkeypatch.setattr(whatsapp, "available", lambda: False)
    refused = client.patch("/api/v1/gym", json=body)
    assert refused.status_code == 422
    assert refused.json()["code"] == "whatsapp_unavailable"
    assert client.get("/api/v1/gym").json()["whatsapp_available"] is False
    monkeypatch.undo()
    saved = client.patch("/api/v1/gym", json=body).json()
    assert saved["settings"]["whatsapp"] is True and saved["whatsapp_available"]


def test_on_a_server_only_with_meta(monkeypatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    assert not whatsapp.available()
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    assert whatsapp.available()


def test_automations_show_the_whatsapp_wording(
    client: TestClient, db: Session, gym: GymFixture
) -> None:
    sign_in(db, client, gym.owner)
    rules = client.get("/api/v1/reminder-rules").json()
    by = {(r["trigger"], r["days"]): r["whatsapp"] for r in rules}
    assert by[("expiry", -7)].startswith("Hi {name}, this is {gym}. Your {plan}")
    assert by[("expiry", 3)].startswith("Hi {name}, this is {gym}. Your {plan}")
    assert "ended" in by[("expiry", 3)]
    assert by[("birthday", 0)] is None
    wording = client.get("/api/v1/sms-templates").json()
    assert wording["whatsapp"] is True
    assert wording["welcome_whatsapp"].startswith("Welcome to {gym}")


# --- the receipt ---------------------------------------------------------------------


def test_a_receipt_on_whatsapp(
    client: TestClient, db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000611")
    _, payment = sell(db, gym, member, paid=1500_00)
    other = make_member(db, gym, phone="9800000612")
    _, not_theirs = sell(db, gym, other, paid=1500_00)
    sign_in(db, client, gym.owner)
    assert client.get(f"/api/v1/payments/{payment.id}/receipt").json()["whatsapp"]
    response = client.post(f"/api/v1/payments/{payment.id}/receipt-whatsapp")
    assert response.status_code == 201
    assert response.json()["channel"] == "whatsapp"
    run_jobs(db)
    sent = meta.sent[-1]
    assert sent.template == "gymbhai_receipt"
    assert sent.values[2:] == [str(payment.receipt_no), "1,500"]
    assert sent.button.startswith(f"{payment.id}.pdf?exp=")
    assert "&sig=" in sent.button
    refused = client.post(f"/api/v1/payments/{not_theirs.id}/receipt-whatsapp")
    assert refused.status_code == 422
    assert not client.get(f"/api/v1/payments/{not_theirs.id}/receipt").json()[
        "whatsapp"
    ]


# --- Meta's webhook ------------------------------------------------------------------


def signed(client: TestClient, payload: dict, secret: str = SECRET):
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        },
    )


def statuses(*rows: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {"statuses": rows}}]}],
    }


def incoming(phone: str, text: str) -> dict:
    message = {"from": f"977{phone}", "id": "wamid.in", "timestamp": "1760000000",
               "type": "text", "text": {"body": text}}  # fmt: skip
    return {"entry": [{"changes": [{"value": {"messages": [message]}}]}]}


@pytest.fixture
def secret(monkeypatch) -> str:
    monkeypatch.setattr(settings, "whatsapp_app_secret", SECRET)
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-me")
    return SECRET


def test_meta_checks_the_address(client: TestClient, secret: str) -> None:
    query = {"hub.mode": "subscribe", "hub.challenge": "1158201444"}
    ok = client.get(
        "/api/v1/whatsapp/webhook", params={**query, "hub.verify_token": "verify-me"}
    )
    assert ok.status_code == 200 and ok.text == "1158201444"
    wrong = client.get(
        "/api/v1/whatsapp/webhook", params={**query, "hub.verify_token": "guess"}
    )
    assert wrong.status_code == 403


def test_only_what_meta_signed(client: TestClient, secret: str) -> None:
    assert signed(client, statuses(), secret="someone-else").status_code == 403
    unsigned = client.post("/api/v1/whatsapp/webhook", json=statuses())
    assert unsigned.status_code == 403
    assert signed(client, statuses()).status_code == 200


def test_no_secret_no_webhook(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", None)
    assert signed(client, statuses()).status_code == 403


def test_delivered_and_read(
    client: TestClient, db: Session, gym: GymFixture, meta, secret
) -> None:
    member = agreed(db, gym, "9800000621")
    tell(db, gym, member)
    run_jobs(db)
    (row,) = messages(db, member)
    read = {"id": row.provider_ref, "status": "read", "timestamp": "1760000200"}
    delivered = {"id": row.provider_ref, "status": "delivered",
                 "timestamp": "1760000100"}  # fmt: skip
    # Out of order, and twice: the first time of each is kept.
    for status in (read, delivered, read):
        assert signed(client, statuses(status)).status_code == 200
    db.refresh(row)
    assert row.read_at == dt.datetime.fromtimestamp(1760000200, dt.UTC)
    assert row.delivered_at == dt.datetime.fromtimestamp(1760000200, dt.UTC)
    sign_in(db, client, gym.owner)
    logged = client.get("/api/v1/sms", params={"member_id": str(member.id)}).json()
    assert logged["items"][0]["channel"] == "whatsapp"
    assert logged["items"][0]["read_at"] is not None


def test_failed_later_gives_the_credit_back_and_sends_the_sms(
    client: TestClient, db: Session, gym: GymFixture, meta, secret
) -> None:
    member = agreed(db, gym, "9800000631")
    tell(db, gym, member)
    run_jobs(db)
    before = sms.balance(db, gym.gym.id)
    (row,) = messages(db, member)
    failed = {
        "id": row.provider_ref,
        "status": "failed",
        "timestamp": "1760000300",
        "errors": [{"code": 131026, "title": "Message undeliverable"}],
    }
    signed(client, statuses(failed))
    signed(client, statuses(failed))  # again: refunded once
    run_jobs(db)
    db.refresh(row)
    db.refresh(member)
    assert row.status == "failed" and "131026" in row.error
    assert member.whatsapp_unreachable_at is not None
    sms_row = messages(db, member)[-1]
    assert sms_row.channel == CHANNEL_SMS and sms_row.status == "sent"
    # +1 back for WhatsApp, −1 for the SMS.
    assert sms.balance(db, gym.gym.id) == before
    refunds = db.scalar(
        select(func.count()).where(SmsCreditLedger.reason == "whatsapp:refund")
    )
    assert refunds == 1


def test_a_reply_once_a_day_free(
    client: TestClient, db: Session, gym: GymFixture, meta, secret
) -> None:
    gym.gym.phone = "9851000000"
    member = agreed(db, gym, "9800000641")
    tell(db, gym, member)
    run_jobs(db)
    before = sms.balance(db, gym.gym.id)
    signed(client, incoming("9800000641", "Hello? Is the gym open on Saturday?"))
    signed(client, incoming("9800000641", "Hello??"))
    run_jobs(db)
    (reply,) = meta.texts
    assert reply[0] == "9800000641"
    assert gym.gym.name in reply[1] and "https://wa.me/9779851000000" in reply[1]
    assert sms.balance(db, gym.gym.id) == before
    # Someone we never wrote to gets nothing.
    signed(client, incoming("9800000649", "Hi"))
    run_jobs(db)
    assert len(meta.texts) == 1


def test_stop(client: TestClient, db: Session, gym: GymFixture, meta, secret) -> None:
    member = agreed(db, gym, "9800000651")
    other_gym = make_gym(db, slug="peak-fitness", phone="9801000077")
    elsewhere = agreed(db, other_gym, "9800000651")
    tell(db, gym, member)
    run_jobs(db)
    signed(client, incoming("9800000651", "STOP"))
    run_jobs(db)
    db.refresh(member)
    db.refresh(elsewhere)
    assert member.whatsapp_agreed_at is None and elsewhere.whatsapp_agreed_at is None
    assert "won't get WhatsApp messages" in meta.texts[-1][1]
    stopped = db.scalars(
        select(ActivityLog.gym_id).where(
            ActivityLog.action == "member.whatsapp_stopped"
        )
    ).all()
    assert set(stopped) == {gym.gym.id, other_gym.gym.id}
    assert tell(db, gym, member) == "sms"


def test_erasing_a_member_clears_it(
    db: Session, gym: GymFixture, meta: FakeWhatsApp
) -> None:
    member = agreed(db, gym, "9800000661")
    tell(db, gym, member)
    run_jobs(db)
    members_service.erase(db, context_for(db, gym.owner), member)
    db.commit()
    (row,) = messages(db, member)
    assert member.whatsapp_agreed_at is None
    assert row.params is None and row.fallback is None and row.body != ""
    assert "Sita" not in row.body
