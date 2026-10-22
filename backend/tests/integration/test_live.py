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


def test_every_staff_screen_hears_about_staff_changes() -> None:
    """Even without any permission: the screen only re-reads who is signed in."""
    nobody = live.staff_filter(staff())
    assert nobody(event(live.STAFF, branch=None))
    assert not nobody(event(live.STAFF, gym=OTHER_GYM, branch=None))


def test_staff_hear_only_their_branches() -> None:
    accepts = live.staff_filter(staff(Permission.MEMBERS_VIEW, branches=[BRANCH]))
    assert accepts(event(live.CHECK_IN))
    assert not accepts(event(live.CHECK_IN, branch=OTHER_BRANCH))
    assert not accepts(event(live.MEMBER, branch=None))


def test_expenses_are_heard_by_staff_who_see_money() -> None:
    """Salaries are among them (PLAN.md §18.1): recording them isn't enough."""
    owner = live.staff_filter(staff(Permission.REPORTS_MONEY))
    assert owner(event(live.EXPENSE)) and owner(event(live.EXPENSE, branch=None))
    recorder = live.staff_filter(
        staff(Permission.MEMBERS_VIEW, Permission.EXPENSES_RECORD)
    )
    assert not recorder(event(live.EXPENSE))
    one_branch = live.staff_filter(staff(Permission.REPORTS_MONEY, branches=[BRANCH]))
    assert one_branch(event(live.EXPENSE))
    assert not one_branch(event(live.EXPENSE, branch=OTHER_BRANCH))
    # The whole gym's: for those who work at every branch.
    assert not one_branch(event(live.EXPENSE, branch=None))


def test_personal_training_is_heard_by_trainers_and_sellers() -> None:
    """The Personal training screens (PLAN.md §18.3). A member's page hears
    the member event sent with each change."""
    assert live.staff_filter(staff(Permission.PT_TRAIN))(event(live.PT))
    assert live.staff_filter(staff(Permission.PT_SELL))(event(live.PT))
    assert not live.staff_filter(staff(Permission.MEMBERS_VIEW))(event(live.PT))
    one_branch = live.staff_filter(staff(Permission.PT_SELL, branches=[BRANCH]))
    assert one_branch(event(live.PT))
    assert not one_branch(event(live.PT, branch=OTHER_BRANCH))


def test_messages_are_heard_by_staff_who_send_sms() -> None:
    """The message log and a member's Messages tab (PLAN.md §19.3): a message
    sent, failed, delivered or read. The whole gym's, as the log is."""
    message = event(live.MESSAGE, branch=None, member=None)
    assert live.staff_filter(staff(Permission.MESSAGES_SMS))(message)
    assert not live.staff_filter(staff(Permission.MEMBERS_VIEW))(message)
    assert not live.staff_filter(staff(Permission.MESSAGES_SMS))(
        event(live.MESSAGE, gym=OTHER_GYM, branch=None, member=None)
    )


def test_the_shop_is_heard_by_who_sells_or_sees_money() -> None:
    """The Shop screen (PLAN.md §20.1): a sale at a branch; the products,
    which are the whole gym's, with no branch."""
    sale = event(live.SHOP)
    products = event(live.SHOP, branch=None, member=None)
    for permission in (
        Permission.SHOP_SELL,
        Permission.SHOP_MANAGE,
        Permission.REPORTS_MONEY,
    ):
        assert live.staff_filter(staff(permission))(sale)
    assert not live.staff_filter(staff(Permission.MEMBERS_VIEW))(sale)
    one_branch = live.staff_filter(staff(Permission.SHOP_SELL, branches=[BRANCH]))
    assert one_branch(sale) and one_branch(products)
    assert not one_branch(event(live.SHOP, branch=OTHER_BRANCH))


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


def test_many_members_told_in_one_statement_each_hear_it(engine: sa.Engine) -> None:
    """Extend everyone tells every member at once (live.members_changed): each
    one's app hears its own event, once, and a member listed twice is told
    once."""
    others = [uuid.uuid4(), uuid.uuid4()]

    def tell_all() -> None:
        with Session(engine) as db:
            live.members_changed(
                db,
                GYM,
                [
                    (MEMBER, BRANCH),
                    (others[0], BRANCH),
                    (MEMBER, BRANCH),
                    (others[1], None),
                ],
            )
            db.commit()

    async def scenario() -> tuple[list[dict], list[dict]]:
        hub = live.Hub(TEST_DATABASE_URL)
        mine = await hub.subscribe(live.member_filter(MEMBER))
        desk = await hub.subscribe(live.staff_filter(staff(Permission.MEMBERS_VIEW)))
        try:
            await asyncio.wait_for(hub.connected.wait(), 5)
            await asyncio.get_running_loop().run_in_executor(None, tell_all)
            heard = [await asyncio.wait_for(mine.queue.get(), 5)]
            await asyncio.sleep(0.3)
            while not mine.queue.empty():
                heard.append(mine.queue.get_nowait())
            seen = []
            while not desk.queue.empty():
                seen.append(desk.queue.get_nowait())
            return heard, seen
        finally:
            await hub.stop()

    heard, seen = asyncio.run(scenario())
    assert [(e["type"], e["member"]) for e in heard] == [(live.MEMBER, str(MEMBER))]
    assert sorted(e["member"] for e in seen) == sorted(
        [str(MEMBER), str(others[0]), str(others[1])]
    )


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


def test_staff_changes_are_published(
    client: TestClient, db: Session, gym_a, make_staff, published
) -> None:
    desk = make_staff(gym_a.gym, permissions=["members.view"])
    sign_in(db, client, gym_a.owner)
    client.patch(f"/api/v1/staff/{desk.id}", json={"permissions": []})
    assert published == [{"gym_id": gym_a.gym.id, "kind": live.STAFF}]

    published.clear()
    client.post(f"/api/v1/staff/{desk.id}/two-step/reset")
    assert [c["kind"] for c in published] == [live.STAFF]


def test_the_gym_requiring_two_step_is_published(
    client: TestClient, db: Session, gym_a, published
) -> None:
    gym_a.owner.totp_nonce = "test-nonce"
    gym_a.owner.totp_enabled_at = gym_a.gym.created_at
    db.commit()
    sign_in(db, client, gym_a.owner)
    response = client.patch("/api/v1/gym/security", json={"require_two_step": True})
    assert response.status_code == 200
    assert published == [{"gym_id": gym_a.gym.id, "kind": live.STAFF}]


def test_platform_admins_publish_nothing(
    db: Session, platform_admin, published
) -> None:
    live.staff_changed(db, platform_admin.gym_id)
    assert published == []
