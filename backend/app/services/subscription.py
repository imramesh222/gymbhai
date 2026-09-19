"""Where a gym stands with us (PLAN.md §5.7).

* Free trial: 14 days from sign-up, no payment details asked.
* Before it ends: a banner, and an SMS to the owner 7 and 2 days before.
* After it ends: 7 days' grace with a red banner, then the staff dashboard is
  read-only — they can see and export everything, but not add members, renew
  or take payments until they pay.
* Members are never punished for the owner's unpaid bill: the member app and
  the door keep working throughout.
* Too many members for the tier: a warning, never a lock-out.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.billing import (
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_TRIAL,
    GymSubscription,
    PlatformPlan,
)
from app.models.member import Member
from app.models.membership import Membership

GRACE_DAYS = 7
WARN_DAYS = 7

OK = "ok"
ENDING = "ending"
GRACE = "grace"
READ_ONLY = "read_only"


@dataclass
class SubscriptionState:
    status: str  # trial, active, none
    plan_name: str | None
    starts_on: dt.date | None
    ends_on: dt.date | None
    # Days of the subscription left, today included; 0 once ended.
    days_left: int
    phase: str  # ok, ending, grace, read_only
    grace_ends_on: dt.date | None
    active_members: int
    max_active_members: int | None

    @property
    def read_only(self) -> bool:
        return self.phase == READ_ONLY

    @property
    def over_limit(self) -> bool:
        return (
            self.max_active_members is not None
            and self.active_members > self.max_active_members
        )


def latest(db: Session, gym_id: uuid.UUID) -> GymSubscription | None:
    return db.scalars(
        select(GymSubscription)
        .where(
            GymSubscription.gym_id == gym_id,
            GymSubscription.status.in_((SUBSCRIPTION_TRIAL, SUBSCRIPTION_ACTIVE)),
        )
        .order_by(GymSubscription.ends_on.desc())
        .limit(1)
    ).first()


def active_member_count(db: Session, gym_id: uuid.UUID, today: dt.date) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(Membership.member_id)))
            .join(Member, Member.id == Membership.member_id)
            .where(
                Membership.gym_id == gym_id,
                Membership.cancelled_at.is_(None),
                Membership.start_date <= today,
                Membership.end_date >= today,
                Member.is_archived.is_(False),
            )
        )
        or 0
    )


def phase_of(ends_on: dt.date | None, today: dt.date) -> str:
    if ends_on is None:
        return READ_ONLY
    if today <= ends_on:
        return ENDING if (ends_on - today).days < WARN_DAYS else OK
    if today <= ends_on + dt.timedelta(days=GRACE_DAYS):
        return GRACE
    return READ_ONLY


def state(
    db: Session, gym_id: uuid.UUID, today: dt.date | None = None, *, count_members=True
) -> SubscriptionState:
    today = today or today_in_nepal()
    row = latest(db, gym_id)
    plan = (
        db.get(PlatformPlan, row.platform_plan_id)
        if row and row.platform_plan_id
        else None
    )
    ends_on = row.ends_on if row else None
    return SubscriptionState(
        status=row.status if row else "none",
        plan_name=plan.name if plan else ("Free trial" if row else None),
        starts_on=row.starts_on if row else None,
        ends_on=ends_on,
        days_left=max((ends_on - today).days + 1, 0) if ends_on else 0,
        phase=phase_of(ends_on, today),
        grace_ends_on=ends_on + dt.timedelta(days=GRACE_DAYS) if ends_on else None,
        active_members=active_member_count(db, gym_id, today) if count_members else 0,
        max_active_members=plan.max_active_members if plan else None,
    )


def is_read_only(db: Session, gym_id: uuid.UUID) -> bool:
    row = latest(db, gym_id)
    return phase_of(row.ends_on if row else None, today_in_nepal()) == READ_ONLY


def extend(
    db: Session,
    gym_id: uuid.UUID,
    *,
    platform_plan_id: uuid.UUID | None,
    months: int | None = None,
    ends_on: dt.date | None = None,
) -> GymSubscription:
    """A paid period, starting when the current one ends (or today if lapsed)."""
    from app.core.calendar import add_months

    today = today_in_nepal()
    current = latest(db, gym_id)
    start = today
    if current is not None and current.ends_on >= today:
        start = current.ends_on + dt.timedelta(days=1)
    if ends_on is None:
        if not months:
            raise ValueError("Give months or an end date.")
        ends_on = add_months(start, months, "ad") - dt.timedelta(days=1)
    row = GymSubscription(
        gym_id=gym_id,
        platform_plan_id=platform_plan_id,
        starts_on=min(start, ends_on),
        ends_on=ends_on,
        status=SUBSCRIPTION_ACTIVE,
    )
    db.add(row)
    db.flush()
    return row
