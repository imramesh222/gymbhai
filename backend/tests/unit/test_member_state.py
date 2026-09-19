import datetime as dt
import uuid

from app.models.membership import Membership, MembershipFreeze
from app.models.payment import Payment
from app.services import memberships as ms
from app.services.members import NONE, state_of

TODAY = dt.date(2026, 9, 19)


def membership(start: str, end: str, *, price=1000, discount=0, fee=0, cancelled=False):
    return Membership(
        id=uuid.uuid4(),
        start_date=dt.date.fromisoformat(start),
        end_date=dt.date.fromisoformat(end),
        price=price,
        discount=discount,
        admission_fee=fee,
        plan_name="1 month",
        cancelled_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC) if cancelled else None,
    )


def paid(m: Membership, amount: int, *, kind="payment", voided=False) -> Payment:
    return Payment(
        membership_id=m.id,
        amount=amount,
        kind=kind,
        voided_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC) if voided else None,
    )


def test_status_is_computed_from_dates() -> None:
    m = membership("2026-09-01", "2026-09-30")
    assert ms.status_of(m, today=TODAY) == ms.ACTIVE
    assert ms.status_of(m, today=dt.date(2026, 8, 31)) == ms.UPCOMING
    assert ms.status_of(m, today=dt.date(2026, 10, 1)) == ms.EXPIRED
    freeze = MembershipFreeze(from_date=TODAY, to_date=TODAY)
    assert ms.status_of(m, [freeze], today=TODAY) == ms.FROZEN
    assert ms.status_of(membership("2026-09-01", "2026-09-30", cancelled=True)) == (
        ms.CANCELLED
    )


def test_the_last_day_counts() -> None:
    m = membership("2026-09-01", "2026-09-19")
    assert ms.status_of(m, today=TODAY) == ms.ACTIVE
    assert ms.days_left(m, today=TODAY) == 1


def test_dues_follow_the_plan_formula() -> None:
    m = membership(
        "2026-09-01", "2026-09-30", price=3000_00, discount=500_00, fee=1000_00
    )
    payments = [
        paid(m, 1000_00),
        paid(m, 700_00),
        paid(m, 900_00, voided=True),
        paid(m, 200_00, kind="refund"),
    ]
    # 3000 - 500 + 1000 - (1000 + 700) + 200
    assert ms.dues_of(m, payments) == 2000_00


def test_a_cancelled_membership_owes_nothing() -> None:
    m = membership("2026-09-01", "2026-09-30", cancelled=True)
    assert ms.dues_of(m, []) == 0


def test_an_early_renewal_extends_days_left() -> None:
    current = membership("2026-09-01", "2026-09-30")
    renewal = membership("2026-10-01", "2026-10-31")
    state = state_of([current, renewal], {}, {}, TODAY)
    assert state.status == ms.ACTIVE
    assert state.current is current
    assert state.valid_until == dt.date(2026, 10, 31)
    assert state.days_left == 43


def test_a_gap_breaks_the_chain() -> None:
    state = state_of(
        [
            membership("2026-09-01", "2026-09-30"),
            membership("2026-11-01", "2026-11-30"),
        ],
        {},
        {},
        TODAY,
    )
    assert state.valid_until == dt.date(2026, 9, 30)


def test_expired_upcoming_and_none() -> None:
    assert state_of([membership("2026-08-01", "2026-08-31")], {}, {}, TODAY).status == (
        ms.EXPIRED
    )
    assert state_of([membership("2026-10-01", "2026-10-31")], {}, {}, TODAY).status == (
        ms.UPCOMING
    )
    assert state_of([], {}, {}, TODAY).status == NONE
    cancelled_only = [membership("2026-09-01", "2026-09-30", cancelled=True)]
    assert state_of(cancelled_only, {}, {}, TODAY).status == NONE
