"""Push to the member app first; SMS only where push can't reach (§16.3, 8.3)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import app.jobs  # noqa: F401  (registers the handlers)
from app import worker
from app.core.time import today_in_nepal, utcnow
from app.models.activity import ActivityLog
from app.models.job import Job
from app.models.messaging import ReminderLog, SmsMessage
from app.models.push import PushSubscription
from app.services import member_auth, reminders
from app.services.push import service as push
from app.services.push.providers import PushError, PushGone, PushMessage, Target
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()
CODE = "123456"


class FakePush:
    """Takes every push, or fails each with `error`."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[Target, PushMessage]] = []
        self.error: Exception | None = None

    def send(self, target: Target, message: PushMessage) -> None:
        if self.error:
            raise self.error
        self.sent.append((target, message))


@pytest.fixture
def provider(monkeypatch) -> FakePush:
    fake = FakePush()
    monkeypatch.setattr(push, "get_provider", lambda target=None: fake)
    return fake


def phone_for(db: Session, member, n: int = 1) -> PushSubscription:
    row = push.subscribe(
        db,
        member,
        endpoint=f"https://push.example.com/send/{member.id}/{n}",
        p256dh="B" * 87,
        auth="a" * 22,
        user_agent="Test phone",
    )
    db.commit()
    return row


def sms_to(db: Session, member) -> list[SmsMessage]:
    return list(db.scalars(select(SmsMessage).where(SmsMessage.member_id == member.id)))


def run_jobs(db: Session) -> None:
    while worker.run_once(db):
        pass


def member_with_month(db: Session, gym: GymFixture, phone: str, ends_in: int = 20):
    member = make_member(db, gym, phone=phone, name=f"Hari {phone[-2:]}")
    sell(db, gym, member, paid=1500_00, start_date=TODAY - dt.timedelta(days=5),
         end_date=TODAY + dt.timedelta(days=ends_in))  # fmt: skip
    return member


def test_turning_push_on_and_off(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: int(CODE))
    member = member_with_month(db, gym_a, "9800000401")
    slug = gym_a.gym.slug
    client.post(f"/api/v1/m/{slug}/otp/request", json={"phone": member.phone})
    token = client.post(
        f"/api/v1/m/{slug}/otp/verify", json={"phone": member.phone, "code": CODE}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    status = client.get("/api/v1/m/me/push").json()
    assert status["public_key"] and status["subscribed"] is False
    endpoint = "https://fcm.googleapis.com/fcm/send/abc123"
    body = {"endpoint": endpoint, "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}
    assert client.post("/api/v1/m/me/push", json=body).json()["subscribed"] is True
    # Again (the browser refreshed its keys): still one subscription.
    assert client.post("/api/v1/m/me/push", json=body).status_code == 200
    assert len(push.live(db, member.id)) == 1
    here = client.get("/api/v1/m/me/push", params={"endpoint": endpoint}).json()
    assert here["subscribed"] is True
    other = client.get("/api/v1/m/me/push", params={"endpoint": endpoint + "x"}).json()
    assert other["subscribed"] is False

    off = client.post("/api/v1/m/me/push/off", json={"endpoint": endpoint})
    assert off.json()["subscribed"] is False
    assert push.live(db, member.id) == []
    actions = set(
        db.scalars(select(ActivityLog.action).where(ActivityLog.actor_id == member.id))
    )
    assert {"push.subscribed", "push.unsubscribed"} <= actions
    # Only https endpoints: a push service, never somewhere of the caller's choosing.
    bad = {**body, "endpoint": "http://10.0.0.1/x"}
    assert client.post("/api/v1/m/me/push", json=bad).status_code == 422


def test_a_notice_goes_by_push_to_those_who_take_it(
    client: TestClient, db: Session, gym_a: GymFixture, provider: FakePush
) -> None:
    with_app = member_with_month(db, gym_a, "9800000411")
    without = member_with_month(db, gym_a, "9800000412")
    phone_for(db, with_app)
    sign_in(db, client, gym_a.owner)
    notice = {"title": "Closed Saturday", "body": "For Tihar.", "send_sms": True}

    cost = client.post("/api/v1/notices/cost", json=notice).json()
    assert (cost["by_push"], cost["by_sms"], cost["total_credits"]) == (1, 1, 1)
    created = client.post("/api/v1/notices", json=notice).json()
    assert (created["push_count"], created["sms_count"]) == (1, 1)
    assert sms_to(db, with_app) == []
    assert len(sms_to(db, without)) == 1

    run_jobs(db)
    [(target, message)] = provider.sent
    assert target.endpoint.endswith(f"{with_app.id}/1")
    assert message.title == "Closed Saturday"
    assert message.url == f"/{gym_a.gym.slug}/notices"
    assert push.live(db, with_app.id)[0].last_ok_at is not None


def test_also_sms(
    client: TestClient, db: Session, gym_a: GymFixture, provider: FakePush
) -> None:
    with_app = member_with_month(db, gym_a, "9800000421")
    phone_for(db, with_app)
    sign_in(db, client, gym_a.owner)
    response = client.patch("/api/v1/sms-templates", json={"also_sms": True})
    assert response.json()["also_sms"] is True
    notice = {"title": "New hours", "body": "6 to 9.", "send_sms": True}
    cost = client.post("/api/v1/notices/cost", json=notice).json()
    assert (cost["by_push"], cost["by_sms"]) == (1, 1)
    client.post("/api/v1/notices", json=notice)
    run_jobs(db)
    assert len(provider.sent) == 1
    assert len(sms_to(db, with_app)) == 1


def test_reminders_go_by_push(db: Session, gym_a: GymFixture, provider) -> None:
    member = member_with_month(db, gym_a, "9800000431", ends_in=7)
    phone_for(db, member)
    assert reminders.run_daily(db) == 1
    db.commit()
    run_jobs(db)
    assert [s for s in sms_to(db, member) if s.kind == "reminder"] == []
    [(_, message)] = provider.sent
    assert message.title == gym_a.gym.name
    assert message.url == f"/{gym_a.gym.slug}/renew"
    log = db.scalars(
        select(ReminderLog).where(ReminderLog.member_id == member.id)
    ).one()
    assert log.sms_message_id is None  # went by push


def test_a_phone_that_is_gone_gets_an_sms_instead(
    db: Session, gym_a: GymFixture, provider: FakePush
) -> None:
    member = member_with_month(db, gym_a, "9800000441", ends_in=7)
    phone_for(db, member)
    provider.error = PushGone("410 Gone")
    reminders.run_daily(db)
    db.commit()
    run_jobs(db)
    assert push.live(db, member.id) == []  # revoked, never tried again
    assert [s.kind for s in sms_to(db, member) if s.kind == "reminder"] == ["reminder"]


def test_a_failing_push_service_is_retried_then_sms(
    db: Session, gym_a: GymFixture, provider: FakePush
) -> None:
    member = member_with_month(db, gym_a, "9800000451", ends_in=7)
    phone_for(db, member)
    provider.error = PushError("503")
    reminders.run_daily(db)
    db.commit()
    for _ in range(worker.MAX_ATTEMPTS):
        db.execute(update(Job).where(Job.done_at.is_(None)).values(run_at=utcnow()))
        db.commit()
        run_jobs(db)
        assert len(push.live(db, member.id)) == 1  # failing isn't gone
    assert [s.kind for s in sms_to(db, member) if s.kind == "reminder"] == ["reminder"]


def test_two_phones_one_works(db: Session, gym_a: GymFixture, monkeypatch) -> None:
    member = member_with_month(db, gym_a, "9800000461", ends_in=7)
    phone_for(db, member, 1)
    gone = phone_for(db, member, 2)

    class OneGone(FakePush):
        def send(self, target, message):
            if target.endpoint == gone.endpoint:
                raise PushGone("410")
            super().send(target, message)

    one = OneGone()
    monkeypatch.setattr(push, "get_provider", lambda target=None: one)
    reminders.run_daily(db)
    db.commit()
    run_jobs(db)
    assert len(one.sent) == 1
    assert [r.endpoint for r in push.live(db, member.id)] != [gone.endpoint]
    assert len(push.live(db, member.id)) == 1
    assert [s for s in sms_to(db, member) if s.kind == "reminder"] == []


def test_erasing_a_member_deletes_their_phones(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = member_with_month(db, gym_a, "9800000471")
    phone_for(db, member)
    sign_in(db, client, gym_a.owner)
    response = client.post(f"/api/v1/members/{member.id}/erase")
    assert response.status_code == 200, response.text
    assert (
        db.scalars(
            select(PushSubscription).where(PushSubscription.member_id == member.id)
        ).all()
        == []
    )


EXPO_TOKEN = "ExponentPushToken[abcdefghij0123456789]"


def app_phone_for(db: Session, member, token: str = EXPO_TOKEN) -> PushSubscription:
    row = push.subscribe_app(db, member, expo_token=token, user_agent="GymBhai app")
    db.commit()
    return row


def test_the_phone_app_turns_push_on_and_off(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    member = member_with_month(db, gym_a, "9800000421")
    issued = member_auth.start_session(db, member, None, "app")
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    # The app needs no VAPID key of ours.
    monkeypatch.setattr(push, "available", lambda: False)

    body = {"kind": "expo", "expo_token": EXPO_TOKEN}
    assert client.post("/api/v1/m/me/push", json=body).json()["subscribed"] is True
    # Twice (a double tap, a retry after a dropped answer): one row.
    assert client.post("/api/v1/m/me/push", json=body).status_code == 200
    [row] = push.live(db, member.id)
    assert (row.kind, row.expo_token, row.endpoint) == ("expo", EXPO_TOKEN, None)
    mine = client.get("/api/v1/m/me/push", params={"expo_token": EXPO_TOKEN})
    assert mine.json()["subscribed"] is True
    assert push.reachable(db, [member.id]) == {member.id}

    for bad in (
        {"kind": "expo", "expo_token": "not-a-token"},
        {"kind": "expo"},
        {"kind": "expo", "expo_token": EXPO_TOKEN, "endpoint": "https://x.y/z"},
    ):
        assert client.post("/api/v1/m/me/push", json=bad).status_code == 422
    # Turning off needs to say which phone.
    assert client.post("/api/v1/m/me/push/off", json={}).status_code == 422
    off = client.post("/api/v1/m/me/push/off", json={"expo_token": EXPO_TOKEN})
    assert off.json()["subscribed"] is False
    assert push.live(db, member.id) == []


def test_without_a_vapid_key_browsers_get_sms_but_the_app_still_gets_push(
    client: TestClient, db: Session, gym_a: GymFixture, provider: FakePush, monkeypatch
) -> None:
    browser = member_with_month(db, gym_a, "9800000431")
    app_user = member_with_month(db, gym_a, "9800000432")
    phone_for(db, browser)
    app_phone_for(db, app_user)
    monkeypatch.setattr(push, "available", lambda: False)
    assert push.reachable(db, [browser.id, app_user.id]) == {app_user.id}
    assert push.reachable_in_gym(db, gym_a.gym.id) == {app_user.id}

    sign_in(db, client, gym_a.owner)
    notice = {"title": "Closed Saturday", "body": "For Tihar.", "send_sms": True}
    created = client.post("/api/v1/notices", json=notice).json()
    assert (created["push_count"], created["sms_count"]) == (1, 1)
    run_jobs(db)
    [(target, _)] = provider.sent
    assert target.is_expo and target.expo_token == EXPO_TOKEN
    assert len(sms_to(db, browser)) == 1 and sms_to(db, app_user) == []


def test_an_app_and_a_browser_both_get_it_and_a_gone_app_is_revoked(
    db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    member = member_with_month(db, gym_a, "9800000441")
    web = phone_for(db, member)
    app = app_phone_for(db, member)
    seen: list[Target] = []

    class Split:
        name = "split"

        def send(self, target: Target, message: PushMessage) -> None:
            seen.append(target)
            if target.is_expo:
                raise PushGone("DeviceNotRegistered")

    monkeypatch.setattr(push, "get_provider", lambda target=None: Split())
    push.handle_send(
        db,
        {"member_id": str(member.id), "title": "T", "body": "B", "url": "/x",
         "fallback": None},
    )  # fmt: skip
    assert {t.is_expo for t in seen} == {True, False}
    assert app.revoked_at is not None and web.revoked_at is None
    assert web.last_ok_at is not None


def test_a_notice_tells_open_apps(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
) -> None:
    from app.services import live

    told: list[dict] = []
    monkeypatch.setattr(live, "publish", lambda db, **event: told.append(event))
    sign_in(db, client, gym_a.owner)
    created = client.post(
        "/api/v1/notices", json={"title": "Hi", "body": "There", "send_sms": False}
    ).json()
    client.delete(f"/api/v1/notices/{created['id']}")
    assert (
        told
        == [
            {"gym_id": gym_a.gym.id, "kind": live.NOTICE, "branch_id": None},
        ]
        * 2
    )
