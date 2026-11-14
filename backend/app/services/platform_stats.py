"""How GymBhai is doing, for /admin (PLAN.md §16.5, 10.1, 10.2).

Revenue, gyms by state, trials that start paying, gyms lost, SMS credits
sold; and each gym's health: last staff sign-in, visits in the last week,
members added in the last month, and its setup checklist. Every figure comes
from a fixed number of queries, however many gyms there are.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.billing import SUBSCRIPTION_ACTIVE, GymSubscription, PlatformPlan
from app.models.gym import GYM_SUSPENDED, Gym
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn
from app.models.payment import GymPaymentMethod
from app.models.plan import Plan
from app.models.platform import KIND_SMS, SubscriptionPayment
from app.models.staff import StaffSession, StaffUser
from app.services import subscription

QUIET_DAYS = 7
NEW_GYM_DAYS = 7
LOST_MONTHS = 6

# The steps a new gym takes (§16.2, 7.4), in the order the checklist shows them.
SETUP_STEPS = (
    "plans_priced",
    "payment_account",
    "logo",
    "staff_invited",
    "poster_printed",
    "first_member",
)


def setups(db: Session, gyms: Sequence[Gym]) -> dict[uuid.UUID, dict[str, bool]]:
    """Each gym's setup steps, done or not: four queries for any number."""
    ids = [g.id for g in gyms]
    if not ids:
        return {}

    def having(*stmt_parts) -> set[uuid.UUID]:
        model, *where = stmt_parts
        return set(
            db.scalars(
                select(model.gym_id).where(model.gym_id.in_(ids), *where).distinct()
            )
        )

    priced = having(Plan, Plan.is_active, Plan.price.is_not(None))
    accounts = having(GymPaymentMethod, GymPaymentMethod.is_active)
    staff = having(StaffUser, StaffUser.is_owner.is_(False))
    members = having(Member)
    return {
        g.id: {
            # Priced, and the gym has said how it counts months (§5.1).
            "plans_priced": g.id in priced and g.config.plan_months is not None,
            "payment_account": g.id in accounts,
            "logo": g.logo_key is not None,
            "staff_invited": g.id in staff,
            "poster_printed": g.config.poster_printed,
            "first_member": g.id in members,
        }
        for g in gyms
    }


@dataclass
class Health:
    last_sign_in_at: dt.datetime | None
    check_ins_7d: int
    members_added_30d: int
    # No staff sign-in and no visits for a week, past its first week.
    going_quiet: bool
    setup: dict[str, bool]

    @property
    def setup_done(self) -> int:
        return sum(self.setup.values())


def health(db: Session, gyms: Sequence[Gym]) -> dict[uuid.UUID, Health]:
    ids = [g.id for g in gyms]
    if not ids:
        return {}
    now = utcnow()
    week_ago = now - dt.timedelta(days=QUIET_DAYS)
    sign_ins = dict(
        db.execute(
            select(StaffUser.gym_id, func.max(StaffSession.created_at))
            .join(StaffUser, StaffUser.id == StaffSession.staff_user_id)
            .where(StaffUser.gym_id.in_(ids))
            .group_by(StaffUser.gym_id)
        ).all()
    )
    visits = dict(
        db.execute(
            select(CheckIn.gym_id, func.count())
            .where(
                CheckIn.gym_id.in_(ids),
                CheckIn.at >= week_ago,
                CheckIn.result.in_(LET_IN),
            )
            .group_by(CheckIn.gym_id)
        ).all()
    )
    added = dict(
        db.execute(
            select(Member.gym_id, func.count())
            .where(
                Member.gym_id.in_(ids), Member.created_at >= now - dt.timedelta(days=30)
            )
            .group_by(Member.gym_id)
        ).all()
    )
    steps = setups(db, gyms)
    out = {}
    for gym in gyms:
        last = sign_ins.get(gym.id)
        settled = gym.created_at < now - dt.timedelta(days=NEW_GYM_DAYS)
        quiet = (
            settled
            and gym.status != GYM_SUSPENDED
            and (last is None or last < week_ago)
            and not visits.get(gym.id)
        )
        out[gym.id] = Health(
            last_sign_in_at=last,
            check_ins_7d=visits.get(gym.id, 0),
            members_added_30d=added.get(gym.id, 0),
            going_quiet=quiet,
            setup=steps[gym.id],
        )
    return out


# --- the numbers -------------------------------------------------------------------


def state_of(gym: Gym, sub: subscription.SubscriptionState) -> str:
    """trial, paying, grace, read_only or suspended: one per gym."""
    if gym.status == GYM_SUSPENDED:
        return "suspended"
    if sub.phase == subscription.READ_ONLY:
        return "read_only"
    if sub.phase == subscription.GRACE:
        return "grace"
    return "paying" if sub.status == SUBSCRIPTION_ACTIVE else "trial"


def _month(day: dt.date) -> str:
    return f"{day.year}-{day.month:02d}"


def _months_back(today: dt.date, count: int) -> list[str]:
    index = today.year * 12 + today.month - 1
    return [
        f"{(index - k) // 12}-{(index - k) % 12 + 1:02d}"
        for k in range(count - 1, -1, -1)
    ]


def summary(db: Session) -> dict[str, Any]:
    today = today_in_nepal()
    gyms = list(db.scalars(select(Gym)))
    states = subscription.states_for(db, [g.id for g in gyms], today)
    by_state = {k: 0 for k in ("trial", "paying", "grace", "read_only", "suspended")}
    for gym in gyms:
        by_state[state_of(gym, states[gym.id])] += 1

    # Monthly recurring revenue: each paying gym's plan at its monthly price.
    latest_paid = {
        r.gym_id: r
        for r in db.scalars(
            select(GymSubscription)
            .where(GymSubscription.status == SUBSCRIPTION_ACTIVE)
            .order_by(GymSubscription.gym_id, GymSubscription.ends_on.desc())
            .distinct(GymSubscription.gym_id)
        )
    }
    prices = dict(db.execute(select(PlatformPlan.id, PlatformPlan.monthly_price)).all())
    mrr = 0
    for gym in gyms:
        row = latest_paid.get(gym.id)
        if (
            row is not None
            and gym.status != GYM_SUSPENDED
            and states[gym.id].phase != subscription.READ_ONLY
            and row.platform_plan_id
        ):
            mrr += prices.get(row.platform_plan_id) or 0

    # Trials that started paying: of gyms past their trial, how many ever paid.
    trial_over = [
        g
        for g in gyms
        if g.created_at.astimezone(NEPAL).date() <= today - dt.timedelta(days=14)
    ]
    converted = sum(1 for g in trial_over if g.id in latest_paid)
    conversion = converted / len(trial_over) if trial_over else None

    # Lost: gyms that had paid, now read-only, by the month they went so.
    months = _months_back(today, LOST_MONTHS)
    lost = {m: 0 for m in months}
    for gym in gyms:
        row = latest_paid.get(gym.id)
        sub = states[gym.id]
        if row is not None and sub.phase == subscription.READ_ONLY and sub.ends_on:
            month = _month(sub.ends_on + dt.timedelta(days=subscription.GRACE_DAYS + 1))
            if month in lost:
                lost[month] += 1

    first = dt.date(int(months[0][:4]), int(months[0][5:]), 1)
    sold = {m: {"credits": 0, "amount": 0} for m in months}
    for reviewed_at, credits, amount in db.execute(
        select(
            SubscriptionPayment.reviewed_at,
            SubscriptionPayment.sms_credits,
            SubscriptionPayment.amount,
        ).where(
            SubscriptionPayment.kind == KIND_SMS,
            SubscriptionPayment.status == "approved",
            SubscriptionPayment.reviewed_at
            >= dt.datetime.combine(first, dt.time(), NEPAL),
        )
    ):
        month = _month(reviewed_at.astimezone(NEPAL).date())
        if month in sold:
            sold[month]["credits"] += credits or 0
            sold[month]["amount"] += amount

    quiet = sum(1 for h in health(db, gyms).values() if h.going_quiet)
    return {
        "mrr": mrr,
        "gyms": len(gyms),
        "by_state": by_state,
        "trial_conversion": conversion,
        "trials_ended": len(trial_over),
        "trials_converted": converted,
        "lost_by_month": [{"month": m, "gyms": lost[m]} for m in months],
        "sms_sold_by_month": [{"month": m, **sold[m]} for m in months],
        "going_quiet": quiet,
    }
