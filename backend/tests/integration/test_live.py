"""Live updates (app/services/live.py): who hears what, and when."""

import asyncio
import json
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.permissions import Permission
from app.models.member_app import METHOD_MANUAL
from app.services import checkins, live
from app.services import memberships as ms
from app.services import payment_requests as requests_service
from tests.conftest import (
    TEST_DATABASE_URL,
    context_for,
    make_member,
    priced_plan,
    sell,
    sign_in,
)

GYM, OTHER_GYM = uuid.uuid4(), uuid.uuid4()
BRANCH, OTHER_BRANCH = uuid.uuid4(), uuid.uuid4()
MEMBER = uuid.uuid4()


def event(kind: str, *, gym=GYM, branch=BRANCH, member=MEMBER) -> dict:
    return {
        "type": kind,
        "gym": str(gym),
        "branch": str(branch) if branch else None,
        "member": str(member),
    }


def staff(*permissions: Permission, branches=None) -> StaffContext:
    return StaffContext(
        staff=None,  # type: ignore[arg-type]
        gym_id=GYM,
        permissions=frozenset(permissions),
        branch_ids=frozenset(branches) if branches is not None else None,
    )


# --- who hears what --------------------------------------------------------------


def test_staff_hear_only_their_own_gym() -> None:
    accepts = live.staff_filter(staff(Permission.MEMBERS_VIEW))
    assert accepts(event(live.CHECK_IN))
    assert not accepts(event(live.CHECK_IN, gym=OTHER_GYM))


def test_staff_hear_only_what_they_could_open() -> None:
    desk = live.staff_filter(staff(Permission.MEMBERS_VIEW))
    assert desk(event(live.MEMBER))
    assert not desk(event(live.PAYMENT_REQUEST))

    approver = live.staff_filter(staff(Permission.PAYMENTS_APPROVE_APP))
    assert approver(event(live.PAYMENT_REQUEST))
    assert not approver(event(live.CHECK_IN))


def test_staff_hear_only_their_branches() -> None:
    accepts = live.staff_filter(staff(Permission.MEMBERS_VIEW, branches=[BRANCH]))
    assert accepts(event(live.CHECK_IN))
    assert not accepts(event(live.CHECK_IN, branch=OTHER_BRANCH))
    assert not accepts(event(live.MEMBER, branch=None))


def test_a_member_hears_only_about_themselves() -> None:
    accepts = live.member_filter(MEMBER)
    assert accepts(event(live.CHECK_IN))
    assert accepts(event(live.PAYMENT_REQUEST))
    assert not accepts(event(live.CHECK_IN, member=uuid.uuid4()))


# --- delivery ----------------------------------------------------------------------


def notify(engine: sa.Engine, *, commit: bool, **kwargs) -> None:
    with Session(engine) as db:
        live.publish(db, gym_id=GYM, **kwargs)
        db.commit() if commit else db.rollback()


def test_events_arrive_only_once_committed(engine: sa.Engine) -> None:
    async def scenario() -> list[dict]:
        hub = live.Hub(TEST_DATABASE_URL)
        subscriber = await hub.subscribe(live.member_filter(MEMBER))
        try:
            await asyncio.wait_for(hub.connected.wait(), 5)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: notify(
                    engine, commit=False, kind=live.MEMBER, member_id=MEMBER
                ),
            )
            await loop.run_in_executor(
                None,
                lambda: notify(
                    engine, commit=True, kind=live.CHECK_IN, member_id=uuid.uuid4()
                ),
            )
            await loop.run_in_executor(
                None,
                lambda: notify(
                    engine, commit=True, kind=live.CHECK_IN, member_id=MEMBER
                ),
            )
            received = [await asyncio.wait_for(subscriber.queue.get(), 5)]
            await asyncio.sleep(0.2)
            while not subscriber.queue.empty():
                received.append(subscriber.queue.get_nowait())
            return received
        finally:
            await hub.stop()

    received = asyncio.run(scenario())
    # Not the rolled-back one, not someone else's: only this member's check-in.
    assert [e["type"] for e in received] == [live.CHECK_IN]
    assert received[0]["member"] == str(MEMBER)


def test_the_stream_is_server_sent_events() -> None:
    class Quiet(live.Hub):
        async def _listen(self) -> None:
            await asyncio.Event().wait()

    async def scenario() -> list[str]:
        hub = Quiet("postgresql://unused")
        chunks = live.stream(live.member_filter(MEMBER), seconds=0.3, source=hub)
        lines = [await anext(chunks)]
        hub.dispatch(event(live.CHECK_IN, member=uuid.uuid4()))  # not theirs
        hub.dispatch(event(live.CHECK_IN))
        lines += [chunk async for chunk in chunks]
        await hub.stop()
        assert not hub.subscribers, "a closed stream must unsubscribe"
        return lines

    lines = asyncio.run(scenario())
    assert lines[0].startswith("retry:")
    assert len(lines) == 2
    name, data = lines[1].strip().split("\n")
    assert name == f"event: {live.CHECK_IN}"
    assert json.loads(data.removeprefix("data: "))["member"] == str(MEMBER)


def test_a_slow_screen_is_told_to_reload() -> None:
    hub = live.Hub("postgresql://unused")
    subscriber = live.Subscriber(lambda e: True)
    hub.subscribers.add(subscriber)
    for _ in range(live.QUEUE_SIZE + 1):
        hub.dispatch(event(live.CHECK_IN))
    assert subscriber.queue.qsize() == 1
    assert subscriber.queue.get_nowait()["type"] == live.RESYNC


def test_streams_need_sign_in(client: TestClient) -> None:
    assert client.get("/api/v1/live").status_code == 401
    assert client.get("/api/v1/m/live").status_code == 401


def test_the_staff_stream_opens(
    client: TestClient, db: Session, gym_a, monkeypatch
) -> None:
    async def once(accepts, *, seconds):
        yield "retry: 3000\n\n"

    monkeypatch.setattr(live, "stream", once)
    sign_in(db, client, gym_a.owner)
    response = client.get("/api/v1/live")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "no-transform" in response.headers["cache-control"]


# --- what publishes ------------------------------------------------------------------


@pytest.fixture
def published(monkeypatch) -> Generator[list[dict]]:
    calls: list[dict] = []
    monkeypatch.setattr(live, "publish", lambda db, **kwargs: calls.append(kwargs))
    yield calls


def test_a_check_in_is_published(db: Session, gym_a, published) -> None:
    member = make_member(db, gym_a)
    checkins.check_in(
        db,
        gym=gym_a.gym,
        member=member,
        branch_id=gym_a.branch.id,
        method=METHOD_MANUAL,
    )
    assert published[-1] == {
        "gym_id": gym_a.gym.id,
        "kind": live.CHECK_IN,
        "member_id": member.id,
        "branch_id": gym_a.branch.id,
    }


def test_sales_and_payments_are_published(db: Session, gym_a, published) -> None:
    member = make_member(db, gym_a)
    membership, _ = sell(db, gym_a, member)
    assert published[-1]["kind"] == live.MEMBER
    assert published[-1]["member_id"] == member.id

    published.clear()
    ms.record_payment(
        db,
        context_for(db, gym_a.owner),
        membership,
        ms.PaymentIn(amount=500_00, method="cash"),
    )
    assert [c["kind"] for c in published] == [live.MEMBER]


def test_payment_requests_are_published(db: Session, gym_a, published) -> None:
    plan = priced_plan(db, gym_a.gym)
    member = make_member(db, gym_a)
    row = requests_service.create(
        db,
        member,
        plan_id=plan.id,
        payment_method_id=None,
        amount=plan.price,
        transaction_ref=None,
    )
    assert published[-1]["kind"] == live.PAYMENT_REQUEST

    published.clear()
    requests_service.reject(db, context_for(db, gym_a.owner), row, "Not received")
    assert [c["kind"] for c in published] == [live.PAYMENT_REQUEST]
    assert published[0]["member_id"] == member.id


def test_an_import_is_published_once(
    client: TestClient, db: Session, gym_a, published
) -> None:
    sign_in(db, client, gym_a.owner)
    register = "Name,Mobile\nHari Thapa,9841111111\nGita Rai,9812222222\n"
    preview = client.post(
        "/api/v1/members/import",
        files={"file": ("register.csv", register.encode(), "text/csv")},
    ).json()
    client.post(f"/api/v1/members/import/{preview['id']}/commit", json={})
    assert published == [
        {"gym_id": gym_a.gym.id, "kind": live.MEMBER, "branch_id": gym_a.branch.id}
    ]
