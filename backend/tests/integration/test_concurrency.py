"""Two requests at once must not both pass a check meant for one.

Unlike the rest of the suite, these tests commit for real, on separate
connections: a row lock only shows up between two transactions. Each test
runs the first request up to just before its commit, holds it open, and
starts the second meanwhile. Without the lock, the second would read the old
state and pass the check too; with it, it waits and sees the first's result.
Everything is truncated afterwards.
"""

import threading
import time
from collections.abc import Callable, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.tenancy import get_in_gym
from app.core.errors import AppError
from app.core.time import utcnow
from app.db.base import Base
from app.models.branded_app import APP_BUILDING, BrandedApp
from app.models.classes import ClassBooking, GymClass
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import DUPLICATE, METHOD_MANUAL, PaymentRequest
from app.models.membership import Membership
from app.models.payment import Payment
from app.services import branded_apps, checkins, classes
from app.services import memberships as ms
from app.services import payment_requests as requests_service
from tests.conftest import (
    GymFixture,
    context_for,
    make_gym,
    make_member,
    priced_plan,
    sell,
)
from tests.integration.test_classes import (
    TOMORROW,
    class_on,
    member_with_plan,
    slot_on,
    zumba,
)

HOLD = 0.5  # how long the first transaction stays open after its write


@pytest.fixture
def sessions(engine: sa.Engine) -> Generator[Callable[[], Session]]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    with engine.begin() as connection:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def gym(sessions: Callable[[], Session]) -> GymFixture:
    with sessions() as db:
        return make_gym(db, slug="race-gym", phone="9841999001")


def race(
    sessions: Callable[[], Session],
    first: Callable[[Session], Any],
    second: Callable[[Session], Any],
) -> tuple[Any, Any]:
    """Run `first`, hold its transaction open, run `second` meanwhile.

    Returns each one's result, or the AppError it raised.
    """
    written = threading.Event()
    results: list[Any] = [None, None]

    def run(index: int, work: Callable[[Session], Any]) -> None:
        with sessions() as db:
            try:
                if index == 1:
                    written.wait(5)
                results[index] = work(db)
                if index == 0:
                    db.flush()
                    written.set()
                    time.sleep(HOLD)
                db.commit()
            except AppError as exc:
                db.rollback()
                results[index] = exc
            finally:
                written.set()

    threads = [
        threading.Thread(target=run, args=(0, first)),
        threading.Thread(target=run, args=(1, second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    return results[0], results[1]


def test_one_payment_request_is_approved_once(sessions, gym: GymFixture) -> None:
    with sessions() as db:
        plan = priced_plan(db, gym.gym)
        member = make_member(db, gym)
        row = requests_service.create(
            db,
            member,
            plan_id=plan.id,
            payment_method_id=None,
            amount=plan.price,
            transaction_ref=None,
        )
        db.commit()
        request_id = row.id

    def approve(db: Session) -> PaymentRequest:
        ctx = context_for(db, gym.owner)
        locked = get_in_gym(db, PaymentRequest, request_id, ctx, for_update=True)
        return requests_service.approve(db, ctx, locked)

    first, second = race(sessions, approve, approve)

    assert isinstance(first, PaymentRequest)
    assert isinstance(second, AppError) and second.code == "request_closed"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Membership)) == 1


def test_two_payments_cannot_both_fit_the_dues(sessions, gym: GymFixture) -> None:
    with sessions() as db:
        member = make_member(db, gym)
        membership, _ = sell(db, gym, member)  # Rs 1,500 owed
        membership_id = membership.id

    def pay_1000(db: Session) -> Payment:
        ctx = context_for(db, gym.owner)
        target = db.get(Membership, membership_id)
        return ms.record_payment(
            db, ctx, target, ms.PaymentIn(amount=1000_00, method="cash")
        )

    first, second = race(sessions, pay_1000, pay_1000)

    assert isinstance(first, Payment)
    assert isinstance(second, AppError) and second.code == "overpayment"
    with sessions() as db:
        paid = db.scalar(select(func.sum(Payment.amount)))
        assert paid == 1000_00


def test_a_double_scan_is_one_visit(sessions, gym: GymFixture) -> None:
    with sessions() as db:
        member = make_member(db, gym)
        sell(db, gym, member, paid=1500_00)
        member_id = member.id

    def scan(db: Session) -> str:
        member = db.get(Member, member_id)
        outcome = checkins.check_in(
            db,
            gym=gym.gym,
            member=member,
            branch_id=gym.branch.id,
            method=METHOD_MANUAL,
        )
        return outcome.check_in.result

    first, second = race(sessions, scan, scan)

    assert first == "allowed"
    assert second == DUPLICATE


def test_two_renewals_at_once_queue_up(sessions, gym: GymFixture) -> None:
    with sessions() as db:
        plan = priced_plan(db, gym.gym)
        plan.admission_fee = 500_00
        db.commit()
        plan_id = plan.id
        member_id = make_member(db, gym).id

    def renew(db: Session) -> Membership:
        ctx = context_for(db, gym.owner)
        membership, _ = ms.sell(
            db,
            ctx,
            db.get(Member, member_id),
            ms.SaleIn(plan_id=plan_id),
            gym.gym.config,
        )
        return membership

    first, second = race(sessions, renew, renew)

    assert second.start_date > first.end_date
    # Only the first membership carries the admission fee.
    assert (first.admission_fee, second.admission_fee) == (500_00, 0)


def test_leaving_the_queue_as_a_place_comes_free_passes_it_on(
    sessions, gym: GymFixture
) -> None:
    """One place, two waiting. The place is given back just as the first in
    the queue (who gets it) leaves: it goes on to the second."""
    with sessions() as db:
        slot = slot_on(db, gym, zumba(db, gym, places=1), TOMORROW)
        gym_class = class_on(db, slot, TOMORROW)
        club = db.get(Gym, gym.gym.id)
        people = [
            member_with_plan(db, gym, f"98120000{i}", name=f"M{i}") for i in range(3)
        ]
        booked, leaving, waiting = (
            classes.book(db, club, m, gym_class).id for m in people
        )
        db.commit()
        class_id = gym_class.id

    def cancel(booking_id) -> Callable[[Session], ClassBooking]:
        def run(db: Session) -> ClassBooking:
            return classes.cancel_booking(
                db,
                db.get(Gym, gym.gym.id),
                db.get(ClassBooking, booking_id),
                db.get(GymClass, class_id),
            )

        return run

    race(sessions, cancel(booked), cancel(leaving))

    with sessions() as db:
        assert db.get(ClassBooking, waiting).status == classes.BOOKED


def test_a_gym_cant_withdraw_an_app_we_have_just_started(
    sessions, gym: GymFixture
) -> None:
    with sessions() as db:
        package, bundle = branded_apps.identifiers("race-gym")
        row = BrandedApp(
            gym_id=gym.gym.id,
            app_name="Race Gym",
            color="#1f6feb",
            android_package=package,
            ios_bundle_id=bundle,
            asked_by=gym.owner.id,
            asked_at=utcnow(),
        )
        db.add(row)
        db.commit()
        app_id = row.id

    def build(db: Session) -> BrandedApp:
        row = db.get(BrandedApp, app_id, with_for_update=True)
        return branded_apps.admin_update(
            db, gym.owner, row, {"status": APP_BUILDING}, None
        )

    def withdraw(db: Session) -> BrandedApp:
        row = branded_apps.of_gym(db, gym.gym.id, for_update=True)
        return branded_apps.withdraw(db, gym.owner, row, None)

    first, second = race(sessions, build, withdraw)

    assert isinstance(first, BrandedApp)
    assert isinstance(second, AppError) and second.code == "app_started"
    with sessions() as db:
        assert db.get(BrandedApp, app_id).status == APP_BUILDING


def test_the_same_payment_sent_twice_at_once_is_saved_once(
    sessions, gym: GymFixture
) -> None:
    """Two taps, both in flight: the second waits on the key, then replays."""
    from types import SimpleNamespace

    from starlette.requests import Request

    from app.api import idempotency
    from app.schemas.money import PaymentCollect

    with sessions() as db:
        membership, _ = sell(db, gym, make_member(db, gym))
        membership_id = membership.id
    payload = PaymentCollect(membership_id=membership_id, amount=500_00, method="cash")

    def tap(db: Session) -> object:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/payments",
                "headers": [(b"idempotency-key", b"double-tap-0001")],
                "query_string": b"",
                "server": ("test", 80),
                "scheme": "http",
                "route": SimpleNamespace(status_code=201),
            }
        )
        ctx = context_for(db, gym.owner)
        try:
            idem = idempotency.begin(db, ctx, request, payload)
        except idempotency.Replay as replay:
            return replay
        payment = ms.record_payment(
            db, ctx, db.get(Membership, membership_id), ms.PaymentIn(500_00, "cash")
        )
        idem.finish(payload)  # any answer will do here
        return payment

    first, second = race(sessions, tap, tap)

    assert isinstance(first, Payment)
    assert isinstance(second, idempotency.Replay)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1


def test_sending_an_sms_holds_up_none_of_the_gyms_other_writes(
    sessions, gym: GymFixture
) -> None:
    """The worker spends SMS credit holding a lock on the gym's row, through
    the gateway's answer. Another send must wait for it (two sends can't spend
    one credit), but nothing else may: every new row checks its foreign key
    against the gym's row. A full lock there stalled the desk for every SMS,
    and deadlocked erasing a member (its SMS rows changed first) with a send."""
    from app.services.sms import service as sms_service

    with sessions() as sending, sessions() as desk, sessions() as other_send:
        sms_service.lock_gym(sending, gym.gym.id)

        desk.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
        make_member(desk, gym)  # inserts and commits, without waiting

        other_send.execute(sa.text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(sa.exc.OperationalError, match="lock timeout"):
            sms_service.lock_gym(other_send, gym.gym.id)
        sending.rollback()
