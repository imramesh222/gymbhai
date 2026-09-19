"""Renewal reminders and the SMS members get at the desk (PLAN.md §5.3, §9).

Reminders run daily at 09:00 Nepal time. For each enabled rule ("7 days
before", "on the day", "3 days after"), members whose membership chain ends
that many days away get one SMS — measured from the END OF THE CHAIN, so
someone who has already renewed is never told they are about to expire.

A reminder is sent at most once per rule per membership (reminder_log), and a
day the worker missed is caught up for up to CATCH_UP_DAYS; {days} in the
text is always the true number.
"""

import datetime as dt
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.calendar import format_date
from app.core.config import settings
from app.core.sms_text import render
from app.core.time import today_in_nepal
from app.models.gym import GYM_ACTIVE, Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.messaging import (
    SMS_MEMBERSHIP,
    SMS_REMINDER,
    SMS_WELCOME,
    ReminderLog,
    ReminderRule,
)
from app.services import members as members_service
from app.services.sms import service as sms

JOB_DAILY = "reminders.daily"
CATCH_UP_DAYS = 2

DEFAULT_RULES = (
    (
        -7,
        "Hi {name}, your {plan} membership at {gym} ends on {end_date}. "
        "Renew any time at the desk or in your app: {link}",
    ),
    (-3, "Hi {name}, {days} days left on your {gym} membership. Renew: {link}"),
    (0, "Hi {name}, your {gym} membership ends today. Renew to keep training: {link}"),
    (
        3,
        "Hi {name}, your {gym} membership ended on {end_date}. "
        "We miss you! Renew at the desk or here: {link}",
    ),
)


def member_link(gym: Gym) -> str:
    return f"{settings.public_app_url.rstrip('/')}/{gym.slug}"


def seed_rules(db: Session, gym_id: uuid.UUID) -> None:
    for days, template in DEFAULT_RULES:
        db.add(ReminderRule(gym_id=gym_id, days_from_expiry=days, template=template))


def values_for(
    gym: Gym, member: Member, membership: Membership | None, end: dt.date | None
) -> dict[str, object]:
    today = today_in_nepal()
    return {
        "name": member.name.split()[0] if member.name else "",
        "gym": gym.name,
        "plan": membership.plan_name if membership else "",
        "end_date": format_date(end, gym.config.date_display) if end else "",
        "days": abs((end - today).days) if end else "",
        "link": member_link(gym),
        "code": member.member_code,
    }


# --- at the desk ------------------------------------------------------------------


def after_sale(
    db: Session,
    gym: Gym,
    member: Member,
    membership: Membership,
    *,
    new_member: bool,
    staff_id: uuid.UUID | None = None,
) -> None:
    """The SMS from §5.3 step 5: welcome for a new member, else "active until"."""
    if not member.app_access:
        return
    state = members_service.state(db, member)
    end = state.valid_until or membership.end_date
    template = gym.config.welcome_sms if new_member else gym.config.membership_sms
    sms.queue(
        db,
        gym_id=gym.id,
        to=member.phone,
        body=render(template, values_for(gym, member, membership, end)),
        kind=SMS_WELCOME if new_member else SMS_MEMBERSHIP,
        member_id=member.id,
        created_by=staff_id,
    )


def welcome(db: Session, gym: Gym, member: Member, staff_id: uuid.UUID | None) -> None:
    """For a member added without a membership, or "Resend welcome" (§5.5)."""
    state = members_service.state(db, member)
    body = render(
        gym.config.welcome_sms,
        values_for(gym, member, state.current, state.valid_until),
    )
    if not state.current:
        body = render(
            "Welcome to {gym}, {name}! Your app: {link}",
            values_for(gym, member, None, None),
        )
    sms.queue(
        db,
        gym_id=gym.id,
        to=member.phone,
        body=body,
        kind=SMS_WELCOME,
        member_id=member.id,
        created_by=staff_id,
    )


def reminder_text(db: Session, gym: Gym, member: Member) -> str:
    """ "Send reminder now" on the Expiring list: the closest rule's wording."""
    state = members_service.state(db, member)
    end = state.valid_until
    rules = list(db.scalars(select(ReminderRule).where(ReminderRule.gym_id == gym.id)))
    template = DEFAULT_RULES[0][1]
    if rules and end is not None:
        offset = (today_in_nepal() - end).days
        template = min(rules, key=lambda r: abs(r.days_from_expiry - offset)).template
    return render(template, values_for(gym, member, state.current, end))


# --- the daily run ------------------------------------------------------------------


def run_daily(db: Session, today: dt.date | None = None) -> int:
    """Queue today's reminders for every gym. Returns how many were queued."""
    today = today or today_in_nepal()
    queued = 0
    for gym in db.scalars(select(Gym).where(Gym.status == GYM_ACTIVE)):
        queued += _run_gym(db, gym, today)
    return queued


def _run_gym(db: Session, gym: Gym, today: dt.date) -> int:
    rules = list(
        db.scalars(
            select(ReminderRule).where(
                ReminderRule.gym_id == gym.id, ReminderRule.enabled
            )
        )
    )
    if not rules:
        return 0
    # Every rule looks at chain ends within [today - d - CATCH_UP, today - d].
    earliest = min(
        today - dt.timedelta(days=r.days_from_expiry + CATCH_UP_DAYS) for r in rules
    )
    latest = max(today - dt.timedelta(days=r.days_from_expiry) for r in rules)
    candidates = list(
        db.scalars(
            select(Member)
            .join(Membership, Membership.member_id == Member.id)
            .where(
                Member.gym_id == gym.id,
                Member.is_archived.is_(False),
                Member.app_access.is_(True),
                Membership.cancelled_at.is_(None),
                Membership.end_date >= earliest,
                Membership.end_date <= latest,
            )
            .distinct()
        )
    )
    states = members_service.states_for(db, candidates, today)
    already: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for rule_id, membership_id in db.execute(
        select(ReminderLog.rule_id, ReminderLog.membership_id).where(
            ReminderLog.gym_id == gym.id
        )
    ):
        already[rule_id].add(membership_id)

    queued = 0
    for member in candidates:
        state = states[member.id]
        end = state.valid_until
        if end is None:
            continue
        # The membership whose end is the chain's end: the one to remind about.
        last = max(
            (
                m
                for m in state.memberships
                if m.cancelled_at is None and m.end_date == end
            ),
            key=lambda m: m.start_date,
            default=None,
        )
        if last is None:
            continue
        for rule in rules:
            target = end + dt.timedelta(days=rule.days_from_expiry)
            if not (target <= today <= target + dt.timedelta(days=CATCH_UP_DAYS)):
                continue
            if last.id in already[rule.id]:
                continue
            # Several rules due at once (a missed day): send only the latest.
            later = [
                r
                for r in rules
                if r.days_from_expiry > rule.days_from_expiry
                and end + dt.timedelta(days=r.days_from_expiry) <= today
            ]
            inserted = db.execute(
                insert(ReminderLog)
                .values(
                    id=uuid.uuid4(),
                    gym_id=gym.id,
                    rule_id=rule.id,
                    membership_id=last.id,
                )
                .on_conflict_do_nothing()
                .returning(ReminderLog.id)
            ).scalar()
            if not inserted or later:
                continue
            message = sms.queue(
                db,
                gym_id=gym.id,
                to=member.phone,
                body=render(rule.template, values_for(gym, member, last, end)),
                kind=SMS_REMINDER,
                member_id=member.id,
            )
            db.execute(
                ReminderLog.__table__.update()
                .where(ReminderLog.id == inserted)
                .values(sms_message_id=message.id)
            )
            queued += 1
    return queued


def handle_daily(db: Session, payload: dict) -> None:
    run_daily(
        db, dt.date.fromisoformat(payload["date"]) if payload.get("date") else None
    )
