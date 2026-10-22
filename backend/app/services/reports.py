"""The Today dashboard and monthly reports (PLAN.md §7).

Every "today" and every month boundary is in Nepal time, and a report month
is a month of the gym's own calendar: a gym showing dates in BS gets BS months
(§10).
"""

import datetime as dt
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import Date, DateTime, Integer, and_, case, column, func, select, values
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import days_in_bs_month, from_bs, to_bs
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.expense import Expense
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn
from app.models.membership import Membership
from app.models.payment import KIND_PAYMENT, Payment
from app.models.staff import StaffUser
from app.models.training import PtPackage, PtPlan, PtSession
from app.services import expenses as expenses_service
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
        conditions.append(ms.payments_in_branches(branches))
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
    not_visiting: int
    expired_but_visiting: list[tuple[uuid.UUID, str, str, dt.datetime]]
    members_with_dues: int
    dues_total: int
    collected: int | None
    collected_by_method: dict[str, int] | None
    active_members: int
    check_ins_by_hour: list[int]
    check_ins_yesterday: int
    collected_yesterday: int | None
    ending_today: list[tuple[uuid.UUID, str, str]]
    top_owing: list[tuple[uuid.UUID, str, int]]


ENDING_SHOWN = 10
OWING_SHOWN = 5


def today(
    db: Session,
    ctx: StaffContext,
    *,
    with_money: bool,
    not_visiting_days: int = GymSettings.model_fields["not_visiting_days"].default,
) -> Today:
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
    by_hour = [0] * 24
    for s in let_in:
        # Nepal keeps one offset all year: hours since its midnight are its hours.
        by_hour[min(23, int((s.at - start).total_seconds() // 3600))] += 1
    yesterday = start - dt.timedelta(days=1)
    same_time_yesterday = now - dt.timedelta(days=1)
    check_ins_yesterday = db.scalar(
        select(func.count())
        .select_from(CheckIn)
        .where(
            CheckIn.gym_id == ctx.gym_id,
            CheckIn.at >= yesterday,
            CheckIn.at < same_time_yesterday,
            CheckIn.result.in_(LET_IN),
            *branch_filter,
        )
    )
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
    ending = sorted(
        (m for m in candidates if states[m.id].valid_until == date),
        key=lambda m: m.name.lower(),
    )
    due_today = len(ending)

    dues = members_service.dues_expression()
    owing = db.execute(
        select(func.count(), func.coalesce(func.sum(dues), 0)).where(
            Member.id.in_(
                members_service.search(ctx, today=date).with_only_columns(Member.id)
            ),
            dues > 0,
        )
    ).one()

    top_owing = db.execute(
        select(Member.id, Member.name, dues)
        .where(
            Member.id.in_(
                members_service.search(ctx, today=date).with_only_columns(Member.id)
            ),
            dues > 0,
        )
        .order_by(dues.desc(), Member.name)
        .limit(OWING_SHOWN)
    ).all()

    active = db.scalar(
        select(func.count()).select_from(
            members_service.search(ctx, status=ms.ACTIVE, today=date).subquery()
        )
    )

    not_visiting = db.scalar(
        select(func.count()).select_from(
            members_service.search(
                ctx, today=date, not_visiting_days=not_visiting_days
            ).subquery()
        )
    )

    collected = by_method = collected_yesterday = None
    if with_money:
        collected, by_method = money_between(
            db, ctx.gym_id, start, start + dt.timedelta(days=1), ctx.branch_ids
        )
        collected_yesterday, _ = money_between(
            db, ctx.gym_id, yesterday, same_time_yesterday, ctx.branch_ids
        )
    return Today(
        date=date,
        check_ins=len(let_in),
        unique_visitors=len({s.member_id for s in let_in}),
        inside_now=list(inside.values()),
        due_today=due_today,
        expiring_this_week=len(candidates),
        not_visiting=not_visiting or 0,
        expired_but_visiting=denied,
        members_with_dues=owing[0],
        dues_total=owing[1],
        collected=collected,
        collected_by_method=by_method,
        active_members=active or 0,
        check_ins_by_hour=by_hour,
        check_ins_yesterday=check_ins_yesterday or 0,
        collected_yesterday=collected_yesterday,
        ending_today=[(m.id, m.name, m.phone) for m in ending[:ENDING_SHOWN]],
        top_owing=[(row.id, row.name, int(row[2])) for row in top_owing],
    )


def setup_checklist(db: Session, gym: Gym) -> dict[str, bool] | None:
    """The steps a new gym still has to take, or None once done or put away."""
    if gym.config.setup_dismissed:
        return None
    from app.services.platform_stats import setups

    steps = setups(db, [gym])[gym.id]
    return None if all(steps.values()) else steps


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
    # Money the gym spent (§18.1), voided expenses left out.
    expenses: int
    expenses_by_category: dict[str, int]
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

    @property
    def profit(self) -> int:
        """Below zero in a month that spent more than came in."""
        return self.income - self.expenses


def months_back(month: str, count: int) -> list[str]:
    """`count` months ending with `month`, oldest first: "2083-06" style.

    AD and BS both have twelve months, so the same arithmetic serves both.
    """
    year, number = (int(x) for x in month.split("-"))
    index = year * 12 + number - 1
    return [
        f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(index - count + 1, index + 1)
    ]


def monthly(db: Session, ctx: StaffContext, month: str) -> Monthly:
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    first, last = month_range(month, calendar)
    start, end = day_start(first), day_start(last + dt.timedelta(days=1))
    today = today_in_nepal()
    as_of = min(last, today)

    income, by_method = money_between(db, ctx.gym_id, start, end, ctx.branch_ids)
    spent, spent_by_category = expenses_service.totals(
        db, ctx.gym_id, first, last, ctx.branch_ids
    )
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
        expenses=spent,
        expenses_by_category=spent_by_category,
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


def trend(db: Session, ctx: StaffContext, months: list[str]) -> list[Monthly]:
    """The figures Reports' charts use, for many months at once (§16.2, 7.9).

    `monthly()` a month at a time costs a dozen queries a month; this costs a
    fixed fifteen or so however many months, each figure grouped by month
    against a table of the months' bounds (BS months aren't calendar months).
    It must agree with `monthly()` exactly: tests hold the two together. The
    breakdowns the charts don't show (by method, category, plan) are empty.
    """
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    today = today_in_nepal()
    spans = [(month, *month_range(month, calendar)) for month in months]
    if not spans:
        return []
    bounds = values(
        column("i", Integer),
        column("first", Date),
        column("last", Date),
        column("as_of", Date),
        column("start", DateTime(timezone=True)),
        column("stop", DateTime(timezone=True)),
        name="month_bounds",
    ).data(
        [
            (
                i,
                first,
                last,
                min(last, today),
                day_start(first),
                day_start(last + dt.timedelta(days=1)),
            )
            for i, (_, first, last) in enumerate(spans)
        ]
    )
    lo, hi = spans[0][1], spans[-1][2]
    lo_start, hi_stop = day_start(lo), day_start(hi + dt.timedelta(days=1))
    member_ids = members_service.search(ctx, today=today).with_only_columns(Member.id)

    def grouped(stmt) -> dict[int, int]:
        return {i: int(n or 0) for i, n in db.execute(stmt.group_by(bounds.c.i)).all()}

    # Money in, as money_between(): refunds subtracted, voids ignored.
    signed = case((Payment.kind == KIND_PAYMENT, Payment.amount), else_=-Payment.amount)
    paid = (
        select(bounds.c.i, func.sum(signed))
        .join_from(
            Payment,
            bounds,
            and_(Payment.paid_at >= bounds.c.start, Payment.paid_at < bounds.c.stop),
        )
        .where(Payment.gym_id == ctx.gym_id, Payment.voided_at.is_(None))
    )
    if ctx.branch_ids is not None:
        paid = paid.where(ms.payments_in_branches(ctx.branch_ids))
    income = grouped(paid)

    spent = grouped(
        expenses_service.in_branches(
            select(bounds.c.i, func.sum(Expense.amount))
            .join_from(
                Expense,
                bounds,
                and_(
                    Expense.spent_on >= bounds.c.first,
                    Expense.spent_on <= bounds.c.last,
                ),
            )
            .where(Expense.gym_id == ctx.gym_id, Expense.voided_at.is_(None)),
            ctx.branch_ids,
        )
    )
    joined = grouped(
        select(bounds.c.i, func.count())
        .join_from(
            Member,
            bounds,
            and_(Member.joined_on >= bounds.c.first, Member.joined_on <= bounds.c.last),
        )
        .where(Member.id.in_(member_ids))
    )
    active = grouped(
        select(bounds.c.i, func.count(func.distinct(Membership.member_id)))
        .join_from(
            Membership,
            bounds,
            and_(
                Membership.start_date <= bounds.c.as_of,
                Membership.end_date >= bounds.c.as_of,
            ),
        )
        .where(Membership.member_id.in_(member_ids), Membership.cancelled_at.is_(None))
    )
    visit_stmt = (
        select(bounds.c.i, func.count())
        .join_from(
            CheckIn,
            bounds,
            and_(CheckIn.at >= bounds.c.start, CheckIn.at < bounds.c.stop),
        )
        .where(CheckIn.gym_id == ctx.gym_id, CheckIn.result.in_(LET_IN))
    )
    if ctx.branch_ids is not None:
        visit_stmt = visit_stmt.where(CheckIn.branch_id.in_(ctx.branch_ids))
    visits = grouped(visit_stmt)

    # Renewals: a membership sold to someone with an earlier one, or their
    # second in the same month; as monthly(), oldest first.
    sold = db.execute(
        select(Membership.member_id, Membership.created_at)
        .where(
            Membership.gym_id == ctx.gym_id,
            Membership.member_id.in_(member_ids),
            Membership.cancelled_at.is_(None),
            Membership.created_at >= lo_start,
            Membership.created_at < hi_stop,
        )
        .order_by(Membership.created_at)
    ).all()
    first_ever = (
        dict(
            db.execute(
                select(Membership.member_id, func.min(Membership.created_at))
                .where(
                    Membership.member_id.in_({m for m, _ in sold}),
                    Membership.cancelled_at.is_(None),
                )
                .group_by(Membership.member_id)
            ).all()
        )
        if sold
        else {}
    )

    # Due to renew: whoever's membership ended in the month; their states once.
    ending = db.execute(
        select(Membership.member_id, Membership.end_date).where(
            Membership.member_id.in_(member_ids),
            Membership.cancelled_at.is_(None),
            Membership.end_date >= lo,
            Membership.end_date <= hi,
        )
    ).all()
    due_ids = {m for m, _ in ending}
    due_members = (
        list(db.scalars(select(Member).where(Member.id.in_(due_ids))))
        if due_ids
        else []
    )
    states = members_service.states_for(db, due_members, today)

    out = []
    for i, (month, first, last) in enumerate(spans):
        start, stop = day_start(first), day_start(last + dt.timedelta(days=1))
        first_time: set[uuid.UUID] = set()
        renewals = 0
        for member_id, created in sold:
            if not start <= created < stop:
                continue
            if first_ever[member_id] < start or member_id in first_time:
                renewals += 1
            else:
                first_time.add(member_id)
        due = {m for m, end in ending if first <= end <= last}
        valid = [states[m].valid_until for m in due]
        out.append(
            Monthly(
                month=month,
                calendar=calendar,
                first_day=first,
                last_day=last,
                income=income.get(i, 0),
                income_by_method={},
                expenses=spent.get(i, 0),
                expenses_by_category={},
                new_members=joined.get(i, 0),
                new_memberships=len(first_time),
                renewals=renewals,
                lapsed=sum(1 for v in valid if v and v <= last and v < today),
                due_to_renew=len(due),
                renewed=sum(1 for v in valid if v and v > last),
                active_members=active.get(i, 0),
                visits=visits.get(i, 0),
            )
        )
    return out


@dataclass
class PtMonth:
    """Personal training in a report month (§18.3)."""

    # Net PT payments: already within the month's income.
    income: int
    sold: int
    sessions: int
    # Members with personal training during the month.
    members: int
    # (trainer id, name, members, sessions trained), busiest first.
    by_trainer: list[tuple[uuid.UUID, str, int, int]]


def pt_month(
    db: Session, ctx: StaffContext, first: dt.date, last: dt.date
) -> PtMonth | None:
    """The month's personal training, at the caller's branches: None for a
    gym that has never had a PT plan. A fixed number of queries."""
    if db.scalar(select(PtPlan.id).where(PtPlan.gym_id == ctx.gym_id).limit(1)) is None:
        return None
    start, end = day_start(first), day_start(last + dt.timedelta(days=1))
    branches = []
    if ctx.branch_ids is not None:
        branches.append(PtPackage.branch_id.in_(ctx.branch_ids))

    signed = case((Payment.kind == KIND_PAYMENT, Payment.amount), else_=-Payment.amount)
    income = db.scalar(
        select(func.coalesce(func.sum(signed), 0))
        .select_from(Payment)
        .join(PtPackage, PtPackage.id == Payment.pt_package_id)
        .where(
            Payment.gym_id == ctx.gym_id,
            Payment.voided_at.is_(None),
            Payment.paid_at >= start,
            Payment.paid_at < end,
            *branches,
        )
    )
    sold = db.scalar(
        select(func.count())
        .select_from(PtPackage)
        .where(
            PtPackage.gym_id == ctx.gym_id,
            PtPackage.cancelled_at.is_(None),
            PtPackage.created_at >= start,
            PtPackage.created_at < end,
            *branches,
        )
    )
    during = (
        PtPackage.gym_id == ctx.gym_id,
        PtPackage.cancelled_at.is_(None),
        PtPackage.start_date <= last,
        PtPackage.end_date >= first,
        *branches,
    )
    members = db.scalar(
        select(func.count(func.distinct(PtPackage.member_id))).where(*during)
    )
    members_by: dict[uuid.UUID, int] = dict(
        db.execute(
            select(PtPackage.trainer_id, func.count(func.distinct(PtPackage.member_id)))
            .where(*during)
            .group_by(PtPackage.trainer_id)
        ).all()
    )
    # Each session counts for the trainer of that day.
    sessions_by: dict[uuid.UUID, int] = dict(
        db.execute(
            select(PtSession.trainer_id, func.count())
            .join(PtPackage, PtPackage.id == PtSession.package_id)
            .where(
                PtSession.gym_id == ctx.gym_id,
                PtSession.voided_at.is_(None),
                PtSession.trained_on >= first,
                PtSession.trained_on <= last,
                *branches,
            )
            .group_by(PtSession.trainer_id)
        ).all()
    )
    trainers = set(members_by) | set(sessions_by)
    names: dict[uuid.UUID, str] = (
        dict(
            db.execute(
                select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(trainers))
            ).all()
        )
        if trainers
        else {}
    )
    by_trainer = sorted(
        (
            (i, names.get(i, ""), members_by.get(i, 0), sessions_by.get(i, 0))
            for i in trainers
        ),
        key=lambda row: (-row[3], -row[2], row[1]),
    )
    return PtMonth(
        income=income or 0,
        sold=sold or 0,
        sessions=sum(sessions_by.values()),
        members=members or 0,
        by_trainer=by_trainer,
    )
