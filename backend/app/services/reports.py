"""The Today dashboard and monthly reports (PLAN.md §7).

Every "today" and every month boundary is in Nepal time, and a report month
is a month of the gym's own calendar: a gym showing dates in BS gets BS months
(§10).
"""

import datetime as dt
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import days_in_bs_month, from_bs, to_bs
from app.core.errors import AppError
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn
from app.models.membership import Membership
from app.models.payment import KIND_PAYMENT, Payment
from app.services import members as members_service
from app.services import memberships as ms

INSIDE_HOURS = 2


def day_start(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(), tzinfo=NEPAL)


def money_between(
    db: Session, gym_id: uuid.UUID, start: dt.datetime, end: dt.datetime, branches=None
) -> tuple[int, dict[str, int]]:
    """Net money received (refunds subtracted, voids ignored), and by method."""
    signed = case((Payment.kind == KIND_PAYMENT, Payment.amount), else_=-Payment.amount)
    conditions = [
        Payment.gym_id == gym_id,
        Payment.voided_at.is_(None),
        Payment.paid_at >= start,
        Payment.paid_at < end,
    ]
    if branches is not None:
        conditions.append(
            Payment.membership_id.in_(
                select(Membership.id).where(Membership.branch_id.in_(branches))
            )
        )
    by_method = dict(
        db.execute(
            select(Payment.method, func.sum(signed))
            .where(*conditions)
            .group_by(Payment.method)
        ).all()
    )
    return sum(by_method.values()), by_method


# --- Today ---


@dataclass
class Today:
    date: dt.date
    check_ins: int
    unique_visitors: int
    inside_now: list[tuple[uuid.UUID, str, dt.datetime]]
    due_today: int
    expiring_this_week: int
    expired_but_visiting: list[tuple[uuid.UUID, str, str, dt.datetime]]
    members_with_dues: int
    dues_total: int
    collected: int | None
    collected_by_method: dict[str, int] | None
    active_members: int


def today(db: Session, ctx: StaffContext, *, with_money: bool) -> Today:
    now = utcnow()
    date = today_in_nepal(now)
    start = day_start(date)
    branch_filter = []
    if ctx.branch_ids is not None:
        branch_filter.append(CheckIn.branch_id.in_(ctx.branch_ids))

    scans = db.execute(
        select(CheckIn.member_id, CheckIn.result, CheckIn.at, Member.name)
        .join(Member, Member.id == CheckIn.member_id)
        .where(CheckIn.gym_id == ctx.gym_id, CheckIn.at >= start, *branch_filter)
        .order_by(CheckIn.at.desc())
    ).all()
    let_in = [s for s in scans if s.result in LET_IN]
    recent = now - dt.timedelta(hours=INSIDE_HOURS)
    inside: dict[uuid.UUID, tuple[uuid.UUID, str, dt.datetime]] = {}
    for s in let_in:
        if s.at >= recent and s.member_id not in inside:
            inside[s.member_id] = (s.member_id, s.name, s.at)
    denied = [
        (s.member_id, s.name, s.result, s.at)
        for s in scans
        if s.result.startswith("denied")
    ][:20]

    # Expiring: members whose chain of memberships ends today / this week.
    candidates = list(
        db.scalars(
            members_service.search(ctx, today=date).where(
                members_service.expiring_filter(date, 7)
            )
        )
    )
    states = members_service.states_for(db, candidates, date)
    due_today = sum(1 for s in states.values() if s.valid_until == date)

    dues = members_service.dues_expression()
    owing = db.execute(
        select(func.count(), func.coalesce(func.sum(dues), 0)).where(
            Member.id.in_(
                members_service.search(ctx, today=date).with_only_columns(Member.id)
            ),
            dues > 0,
        )
    ).one()

    active = db.scalar(
        select(func.count()).select_from(
            members_service.search(ctx, status=ms.ACTIVE, today=date).subquery()
        )
    )

    collected = by_method = None
    if with_money:
        collected, by_method = money_between(
            db, ctx.gym_id, start, start + dt.timedelta(days=1), ctx.branch_ids
        )
    return Today(
        date=date,
        check_ins=len(let_in),
        unique_visitors=len({s.member_id for s in let_in}),
        inside_now=list(inside.values()),
        due_today=due_today,
        expiring_this_week=len(candidates),
        expired_but_visiting=denied,
        members_with_dues=owing[0],
        dues_total=owing[1],
        collected=collected,
        collected_by_method=by_method,
        active_members=active or 0,
    )


# --- monthly ---


def month_range(month: str, calendar: str) -> tuple[dt.date, dt.date]:
    """First and last day (inclusive) of "2083-06" (BS) or "2026-09" (AD)."""
    try:
        year, number = (int(x) for x in month.split("-"))
        if not 1 <= number <= 12:
            raise ValueError
        if calendar == "bs":
            first = from_bs(year, number, 1)
            last = from_bs(year, number, days_in_bs_month(year, number))
        else:
            first = dt.date(year, number, 1)
            following = dt.date(year + number // 12, number % 12 + 1, 1)
            last = following - dt.timedelta(days=1)
    except (ValueError, KeyError, IndexError) as exc:
        raise AppError(422, "bad_month", "Month must look like 2083-06.") from exc
    return first, last


def current_month(calendar: str, today: dt.date | None = None) -> str:
    today = today or today_in_nepal()
    if calendar == "bs":
        year, month, _ = to_bs(today)
        return f"{year}-{month:02d}"
    return f"{today.year}-{today.month:02d}"


@dataclass
class Monthly:
    month: str
    calendar: str
    first_day: dt.date
    last_day: dt.date
    income: int
    income_by_method: dict[str, int]
    new_members: int
    new_memberships: int
    renewals: int
    lapsed: int
    due_to_renew: int
    renewed: int
    active_members: int
    visits: int
    by_plan: dict[str, int] = field(default_factory=dict)

    @property
    def renewal_rate(self) -> float | None:
        return round(self.renewed / self.due_to_renew, 3) if self.due_to_renew else None


def monthly(db: Session, ctx: StaffContext, month: str) -> Monthly:
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    first, last = month_range(month, calendar)
    start, end = day_start(first), day_start(last + dt.timedelta(days=1))
    today = today_in_nepal()
    as_of = min(last, today)

    income, by_method = money_between(db, ctx.gym_id, start, end, ctx.branch_ids)
    scope = members_service.search(ctx, today=as_of)
    member_ids = scope.with_only_columns(Member.id)

    new_members = db.scalar(
        select(func.count()).where(
            Member.id.in_(member_ids),
            Member.joined_on >= first,
            Member.joined_on <= last,
        )
    )

    sold = list(
        db.scalars(
            select(Membership).where(
                Membership.gym_id == ctx.gym_id,
                Membership.member_id.in_(member_ids),
                Membership.cancelled_at.is_(None),
                Membership.created_at >= start,
                Membership.created_at < end,
            )
        )
    )
    earlier = set(
        db.scalars(
            select(Membership.member_id).where(
                Membership.member_id.in_([m.member_id for m in sold]),
                Membership.cancelled_at.is_(None),
                Membership.created_at < start,
            )
        )
    )
    first_time: set[uuid.UUID] = set()
    renewals = 0
    for m in sorted(sold, key=lambda m: m.created_at):
        if m.member_id in earlier or m.member_id in first_time:
            renewals += 1
        else:
            first_time.add(m.member_id)
    by_plan = Counter(m.plan_name for m in sold)

    # Due to renew: whoever's membership ended during the month. Renewed:
    # those whose chain now runs past it.
    due_members = list(
        db.scalars(
            select(Member)
            .join(Membership, Membership.member_id == Member.id)
            .where(
                Member.id.in_(member_ids),
                Membership.cancelled_at.is_(None),
                Membership.end_date >= first,
                Membership.end_date <= last,
            )
            .distinct()
        )
    )
    states = members_service.states_for(db, due_members, today)
    renewed = sum(1 for s in states.values() if s.valid_until and s.valid_until > last)
    lapsed = sum(
        1
        for s in states.values()
        if s.valid_until and s.valid_until <= last and s.valid_until < today
    )

    active = db.scalar(
        select(func.count(func.distinct(Membership.member_id))).where(
            Membership.member_id.in_(member_ids),
            Membership.cancelled_at.is_(None),
            and_(Membership.start_date <= as_of, Membership.end_date >= as_of),
        )
    )
    branch_filter = []
    if ctx.branch_ids is not None:
        branch_filter.append(CheckIn.branch_id.in_(ctx.branch_ids))
    visits = db.scalar(
        select(func.count()).where(
            CheckIn.gym_id == ctx.gym_id,
            CheckIn.result.in_(LET_IN),
            CheckIn.at >= start,
            CheckIn.at < end,
            *branch_filter,
        )
    )
    return Monthly(
        month=month,
        calendar=calendar,
        first_day=first,
        last_day=last,
        income=income,
        income_by_method=by_method,
        new_members=new_members or 0,
        new_memberships=len(first_time),
        renewals=renewals,
        lapsed=lapsed,
        due_to_renew=len(due_members),
        renewed=renewed,
        active_members=active or 0,
        visits=visits or 0,
        by_plan=dict(by_plan),
    )
