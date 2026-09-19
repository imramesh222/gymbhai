"""SMS to gym owners: subscription reminders, daily summary (PLAN.md §5.7, §9)."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import format_date
from app.core.permissions import ALL_PERMISSIONS
from app.core.time import today_in_nepal
from app.models.gym import GYM_ACTIVE, Gym
from app.models.messaging import SMS_PLATFORM, SMS_SUMMARY
from app.models.staff import StaffUser
from app.services import reports, subscription
from app.services.sms import service as sms

JOB_SUBSCRIPTION = "subscription.reminders"
JOB_SUMMARY = "owners.daily_summary"
REMIND_DAYS_LEFT = (7, 2)


def _owner(db: Session, gym: Gym) -> StaffUser | None:
    return db.scalars(
        select(StaffUser).where(
            StaffUser.gym_id == gym.id, StaffUser.is_owner, StaffUser.is_active
        )
    ).first()


def subscription_reminders(db: Session, today: dt.date | None = None) -> int:
    """7 and 2 days before the end, and on the first day of grace. On us."""
    today = today or today_in_nepal()
    sent = 0
    for gym in db.scalars(select(Gym).where(Gym.status == GYM_ACTIVE)):
        row = subscription.latest(db, gym.id)
        if row is None:
            continue
        left = (row.ends_on - today).days + 1
        owner = _owner(db, gym)
        if owner is None or not owner.phone:
            continue
        if left in REMIND_DAYS_LEFT:
            text = (
                f"GymBhai: {gym.name}'s subscription ends on {row.ends_on:%d %b %Y} "
                f"({left} days). Pay from Settings > Subscription to keep going."
            )
        elif left == 0:
            text = (
                f"GymBhai: {gym.name}'s subscription has ended. You have "
                f"{subscription.GRACE_DAYS} days to pay before the dashboard becomes "
                "read-only. Your members' app and the door keep working."
            )
        else:
            continue
        sms.queue(db, gym_id=gym.id, to=owner.phone, body=text, kind=SMS_PLATFORM)
        sent += 1
    return sent


def daily_summaries(db: Session) -> int:
    """ "Today: 42 visits, Rs 18,500 collected, 6 expiring this week" (§9)."""
    sent = 0
    for gym in db.scalars(select(Gym).where(Gym.status == GYM_ACTIVE)):
        if not gym.config.daily_summary_sms:
            continue
        owner = _owner(db, gym)
        if owner is None or not owner.phone:
            continue
        ctx = StaffContext(
            staff=owner, gym_id=gym.id, permissions=ALL_PERMISSIONS, branch_ids=None
        )
        day = reports.today(db, ctx, with_money=True)
        rupees = f"{(day.collected or 0) / 100:,.0f}"
        text = (
            f"{gym.name} {format_date(day.date, 'ad')}: {day.check_ins} visits, "
            f"Rs {rupees} collected, {day.expiring_this_week} expiring this week"
            + (
                f", {len(day.expired_but_visiting)} turned away"
                if day.expired_but_visiting
                else ""
            )
            + "."
        )
        sms.queue(db, gym_id=gym.id, to=owner.phone, body=text, kind=SMS_SUMMARY)
        sent += 1
    return sent
