"""Notifications for staff about what members did (PLAN.md §18.6)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import app.jobs  # noqa: F401  (registers the handlers)
from app import worker
from app.core.time import today_in_nepal, utcnow
from app.models.activity import ActivityLog
from app.models.gym import Branch
from app.models.job import Job
from app.models.push import StaffPushSubscription
from app.services import freeze_requests, payment_requests, sessions
from app.services import leads as leads_service
from app.services.push import staff as staff_push
from app.services.push.providers import PushError, PushGone, PushMessage, Target
from tests.conftest import GymFixture, make_member, priced_plan, sell

TODAY = today_in_nepal()
APPROVE = ["payments.approve_app", "members.view"]


class FakePush:
    """Takes every push, or fails each with `error`."""

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
    monkeypatch.setattr(staff_push, "get_provider", lambda target=None: fake)
    return fake


def endpoint_of(staff, n: int = 1) -> str:
    return f"https://push.example.com/staff/{staff.id}/{n}"


def signed_in(db: Session, client: TestClient, staff):
    """A real sign-in for `staff`, used by `client`; its session."""
    issued = sessions.start(db, staff, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    return issued.session


def turn_on(client: TestClient, staff, n: int = 1):
    return client.post(
        "/api/v1/auth/push",
        json={
            "endpoint": endpoint_of(staff, n),
            "keys": {"p256dh": "B" * 87, "auth": "a" * 22},
        },
    )


def browser_on(db: Session, staff, n: int = 1) -> StaffPushSubscription:
    """A browser of `staff` that takes notifications, without the API."""
    issued = sessions.start(db, staff, None)
    row = staff_push.subscribe(
        db,
        staff,
        issued.session,
        endpoint=endpoint_of(staff, n),
        p256dh="B" * 87,
        auth="a" * 22,
        user_agent="Test phone",
    )
    db.commit()
    return row


def run_jobs(db: Session) -> None:
    while worker.run_once(db):
        pass


def staff_jobs(db: Session) -> list[dict]:
    return [
        job.payload
        for job in db.scalars(
            select(Job)
            .where(Job.kind == staff_push.JOB_STAFF_PUSH)
            .order_by(Job.created_at)
        )
    ]


def ask_to_pay(db: Session, gym: GymFixture, member):
    row = payment_requests.create(
        db,
        member,
        plan_id=priced_plan(db, gym.gym).id,
        payment_method_id=None,
        amount=1500_00,
        transaction_ref=None,
    )
    db.commit()
    return row


# --- turning it on ----------------------------------------------------------------


def test_turning_it_on_and_off_in_a_browser(
    client: TestClient, db: Session, gym_a: GymFixture
):
    signed_in(db, client, gym_a.owner)
    here = {"endpoint": endpoint_of(gym_a.owner)}
    status = client.get("/api/v1/auth/push", params=here).json()
    assert status["public_key"]
    assert status["on_here"] is False
    # The owner may see all three.
    assert status["kinds"] == ["payment_request", "freeze_request", "lead"]

    assert turn_on(client, gym_a.owner).json()["on_here"] is True
    # Twice is harmless: the same browser, one row.
    assert turn_on(client, gym_a.owner).status_code == 200
    assert db.scalar(select(func.count()).select_from(StaffPushSubscription)) == 1
    assert client.get("/api/v1/auth/push", params=here).json()["on_here"] is True

    off = client.post("/api/v1/auth/push/off", json=here).json()
    assert off["on_here"] is False
    actions = db.scalars(
        select(ActivityLog.action).where(ActivityLog.action.like("staff.push_%"))
    ).all()
    assert sorted(actions) == ["staff.push_off", "staff.push_on", "staff.push_on"]


def test_only_the_kinds_they_may_get(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    signed_in(db, client, make_staff(gym_a.gym, permissions=["leads.manage"]))
    assert client.get("/api/v1/auth/push").json()["kinds"] == ["lead"]
    signed_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert client.get("/api/v1/auth/push").json()["kinds"] == []


def test_without_a_vapid_key_nothing_is_on(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
):
    monkeypatch.setattr(staff_push, "available", lambda: False)
    signed_in(db, client, gym_a.owner)
    refused = turn_on(client, gym_a.owner)
    assert (refused.status_code, refused.json()["code"]) == (409, "push_unavailable")


def test_nobody_turns_off_anyone_elses(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    theirs = browser_on(db, gym_a.owner)
    signed_in(db, client, make_staff(gym_a.gym, permissions=APPROVE))
    client.post("/api/v1/auth/push/off", json={"endpoint": theirs.endpoint})
    db.refresh(theirs)
    assert theirs.revoked_at is None


# --- who gets what ----------------------------------------------------------------


def test_a_payment_from_the_app_reaches_the_approvers(
    db: Session, gym_a: GymFixture, make_staff, provider
):
    approver = make_staff(gym_a.gym, permissions=APPROVE)
    desk = make_staff(gym_a.gym, permissions=["members.view", "payments.collect"])
    for person in (gym_a.owner, approver, desk):
        browser_on(db, person)
    member = make_member(db, gym_a)
    ask_to_pay(db, gym_a, member)

    assert {job["staff_id"] for job in staff_jobs(db)} == {
        str(gym_a.owner.id),
        str(approver.id),
    }
    run_jobs(db)
    assert len(provider.sent) == 2
    target, message = provider.sent[0]
    assert target.endpoint.startswith("https://push.example.com/staff/")
    assert (message.title, message.body) == (
        "Payment to approve",
        "Sita Rai: Rs 1,500 for 1 month",
    )
    assert (message.url, message.tag) == ("/staff/payment-requests", "payment_request")

    # A second one waiting: the newest replaces the last, with the count.
    other = make_member(db, gym_a, name="Ram Thapa", phone="9812345679")
    ask_to_pay(db, gym_a, other)
    run_jobs(db)
    assert provider.sent[-1][1].title == "2 payments to approve"


def test_in_their_own_language(db: Session, gym_a: GymFixture, make_staff, provider):
    approver = make_staff(gym_a.gym, permissions=APPROVE)
    approver.language = "ne"
    browser_on(db, approver)
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    run_jobs(db)
    [(_, message)] = provider.sent
    assert message.title == "स्वीकृत गर्नुपर्ने एप भुक्तानी"
    assert message.body == "Sita Rai: 1 month का लागि Rs 1,500"


def test_freeze_requests_go_by_the_members_branch(
    db: Session, gym_a: GymFixture, make_staff, provider
):
    koteshwor = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(koteshwor)
    db.commit()
    freeze = ["memberships.freeze", "members.view"]
    here = make_staff(gym_a.gym, permissions=freeze, branches=[gym_a.branch])
    there = make_staff(gym_a.gym, permissions=freeze, branches=[koteshwor])
    everywhere = make_staff(gym_a.gym, permissions=freeze)
    for person in (here, there, everywhere):
        browser_on(db, person)
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    freeze_requests.create(
        db,
        member,
        from_date=TODAY,
        to_date=TODAY + dt.timedelta(days=9),
        reason="Going home for Tihar",
    )
    db.commit()

    assert {job["staff_id"] for job in staff_jobs(db)} == {
        str(here.id),
        str(everywhere.id),
    }
    run_jobs(db)
    message = provider.sent[0][1]
    assert message.title == "Freeze request"
    assert message.body.startswith("Sita Rai: 10 days from ")
    assert message.url == "/staff/freeze-requests"


def test_an_enquiry_from_the_join_form(
    db: Session, gym_a: GymFixture, make_staff, provider
):
    handler = make_staff(gym_a.gym, permissions=["leads.manage"])
    browser_on(db, handler)
    values = {"name": "Ram Thapa", "phone": "9800000001", "branch_id": None}
    leads_service.from_join_form(db, gym_a.gym, values, "203.0.113.9")
    db.commit()
    run_jobs(db)
    [(_, message)] = provider.sent
    assert (message.title, message.body, message.url) == (
        "New enquiry",
        "Ram Thapa, 9800000001",
        "/staff/enquiries",
    )
    # Asking again moves it up today's calls; nobody is told twice.
    leads_service.from_join_form(db, gym_a.gym, values, "203.0.113.9")
    db.commit()
    run_jobs(db)
    assert len(provider.sent) == 1


def test_the_ticks_turn_kinds_off(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    person = make_staff(gym_a.gym, permissions=[*APPROVE, "leads.manage"])
    signed_in(db, client, person)
    turn_on(client, person)
    chosen = client.put(
        "/api/v1/auth/me/notifications",
        json={"muted": ["lead"], "endpoint": endpoint_of(person)},
    ).json()
    assert (chosen["muted"], chosen["on_here"]) == (["lead"], True)

    leads_service.from_join_form(
        db, gym_a.gym, {"name": "Ram", "phone": "9800000002"}, None
    )
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    assert [job["tag"] for job in staff_jobs(db)] == ["payment_request"]


def test_signing_out_stops_them_and_signing_in_again_picks_them_up(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    person = make_staff(gym_a.gym, permissions=APPROVE)
    first = signed_in(db, client, person)
    turn_on(client, person)
    # Signed out from another device: a lost phone.
    first.revoked_at = utcnow()
    db.commit()
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    assert staff_jobs(db) == []

    # The same person signs in again in that browser: on again, unasked.
    signed_in(db, client, person)
    here = {"endpoint": endpoint_of(person)}
    assert client.get("/api/v1/auth/push", params=here).json()["on_here"] is False
    assert client.post("/api/v1/auth/push/resume", json=here).json()["on_here"]
    # Asked again on the next page load: still on, nothing to change.
    assert client.post("/api/v1/auth/push/resume", json=here).json()["on_here"]
    ask_to_pay(db, gym_a, make_member(db, gym_a, name="Ram", phone="9812345679"))
    assert [job["staff_id"] for job in staff_jobs(db)] == [str(person.id)]


def test_someone_else_signing_in_there_starts_with_them_off(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    first, second = (make_staff(gym_a.gym, permissions=APPROVE) for _ in range(2))
    session = signed_in(db, client, first)
    turn_on(client, first)
    session.revoked_at = utcnow()
    db.commit()

    signed_in(db, client, second)
    # The browser asks to pick them up again: not for someone else.
    here = {"endpoint": endpoint_of(first)}
    assert client.post("/api/v1/auth/push/resume", json=here).json()["on_here"] is False
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    assert staff_jobs(db) == []


def test_a_disabled_account_or_a_removed_permission_gets_nothing(
    db: Session, gym_a: GymFixture, make_staff
):
    gone = make_staff(gym_a.gym, permissions=APPROVE)
    moved = make_staff(gym_a.gym, permissions=APPROVE)
    for person in (gone, moved):
        browser_on(db, person)
    gone.is_active = False
    moved.permissions = ["members.view"]
    db.commit()
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    assert staff_jobs(db) == []


def test_another_gyms_staff_never_hear(
    db: Session, gym_a: GymFixture, gym_b: GymFixture
):
    browser_on(db, gym_b.owner)
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    assert staff_jobs(db) == []


# --- sending ----------------------------------------------------------------------


def test_a_browser_that_is_gone_is_turned_off(db: Session, gym_a: GymFixture, provider):
    row = browser_on(db, gym_a.owner)
    provider.error = PushGone("410")
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    run_jobs(db)
    db.refresh(row)
    assert row.revoked_at is not None


def test_a_failing_push_service_is_retried(db: Session, gym_a: GymFixture, provider):
    row = browser_on(db, gym_a.owner)
    provider.error = PushError("503")
    ask_to_pay(db, gym_a, make_member(db, gym_a))
    run_jobs(db)
    job = db.scalars(select(Job).where(Job.kind == staff_push.JOB_STAFF_PUSH)).one()
    assert job.done_at is None and job.attempts == 1
    # Failing for now isn't gone: tried again later, and it arrives.
    provider.error = None
    db.execute(update(Job).where(Job.done_at.is_(None)).values(run_at=utcnow()))
    db.commit()
    run_jobs(db)
    assert len(provider.sent) == 1
    db.refresh(row)
    assert row.revoked_at is None and row.last_ok_at is not None
