"""Automations and the SMS members get at the desk (PLAN.md §5.3, §9, §16.3 8.2).

Automations run daily at 09:00 Nepal time. Each enabled rule has a trigger:

- expiry: the membership chain ends `days` away ("7 days before", "on the
  day"). Measured from the END OF THE CHAIN, so someone who has already
  renewed is never told they are about to expire.
- lapsed: the chain ended `days` ago and they haven't renewed (win-back).
- dues: money still owed on a membership `days` after it was sold.
- not_visiting: active, and no visit for `days` days.
- birthday: on the member's birthday.

Nothing is sent twice: reminder_log holds one row per rule and occasion (its
`dedupe_key`). A day the worker missed is caught up for up to CATCH_UP_DAYS;
{days} in the text is always the true number.
"""

import calendar
import datetime as dt
import uuid
from collections import defaultdict

from sqlalchemy import extract, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import sms_defaults
from app.core.calendar import format_date
from app.core.config import settings
from app.core.sms_text import render
from app.core.time import NEPAL, today_in_nepal
from app.models.gym import GYM_ACTIVE, Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.messaging import (
    SMS_MEMBERSHIP,
    SMS_REMINDER,
    SMS_WELCOME,
    TRIGGER_BIRTHDAY,
    TRIGGER_DUES,
    TRIGGER_EXPIRY,
    TRIGGER_LAPSED,
    TRIGGER_NOT_VISITING,
    ReminderLog,
    ReminderRule,
)
from app.services import members as members_service
from app.services import memberships as ms
from app.services.push import service as push
from app.services.sms import service as sms

JOB_DAILY = "reminders.daily"
CATCH_UP_DAYS = 2


def member_link(gym: Gym) -> str:
    return f"{settings.public_app_url.rstrip('/')}/{gym.slug}"


def seed_rules(db: Session, gym_id: uuid.UUID, language: str = "en") -> None:
    """Expiry reminders on; the other automations there, but off (§16.3, 8.2)."""
    for trigger, days, template, enabled in sms_defaults.RULES[language]:
        db.add(
            ReminderRule(
                gym_id=gym_id,
                trigger=trigger,
                days=days,
                template=template,
                enabled=enabled,
            )
        )


def switch_language(db: Session, gym: Gym, old: str, new: str) -> None:
    """The gym changed language: wording it never edited follows (§16.6).
    Anything the gym wrote itself stays as written."""
    config = gym.config
    changes = {}
    if config.welcome_sms == sms_defaults.WELCOME[old]:
        changes["welcome_sms"] = sms_defaults.WELCOME[new]
    if config.membership_sms == sms_defaults.MEMBERSHIP[old]:
        changes["membership_sms"] = sms_defaults.MEMBERSHIP[new]
    if changes:
        gym.settings = {**gym.settings, **changes}
    was = {(t, d): text for t, d, text, _ in sms_defaults.RULES[old]}
    now = {(t, d): text for t, d, text, _ in sms_defaults.RULES[new]}
    for rule in db.scalars(select(ReminderRule).where(ReminderRule.gym_id == gym.id)):
        key = (rule.trigger, rule.days)
        if key in now and rule.template == was.get(key):
            rule.template = now[key]


def values_for(
    gym: Gym,
    member: Member,
    membership: Membership | None,
    end: dt.date | None,
    **extra: object,
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
        **extra,
    }


def rupees(paisa: int) -> str:
    return f"{paisa / 100:,.0f}"


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
    body = render(template, values_for(gym, member, membership, end))
    if new_member:
        # The welcome carries the app's link: it goes before they can have push.
        sms.queue(
            db,
            gym_id=gym.id,
            to=member.phone,
            body=body,
            kind=SMS_WELCOME,
            member_id=member.id,
            created_by=staff_id,
        )
        return
    push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=body,
        url=f"/{gym.slug}",
        tag="membership",
        sms_body=body,
        sms_kind=SMS_MEMBERSHIP,
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
            sms_defaults.WELCOME_NO_PLAN[gym.config.language],
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
    """ "Send reminder now" on Follow up: the closest expiry rule's wording."""
    state = members_service.state(db, member)
    end = state.valid_until
    rules = list(
        db.scalars(
            select(ReminderRule).where(
                ReminderRule.gym_id == gym.id,
                ReminderRule.trigger.in_((TRIGGER_EXPIRY, TRIGGER_LAPSED)),
            )
        )
    )
    template = sms_defaults.RULES[gym.config.language][0][2]
    if rules and end is not None:
        offset = (today_in_nepal() - end).days
        template = min(rules, key=lambda r: abs(_offset(r) - offset)).template
    return render(template, values_for(gym, member, state.current, end))


# --- the daily run ------------------------------------------------------------------


def run_daily(db: Session, today: dt.date | None = None) -> int:
    """Queue today's reminders for every gym. Returns how many were queued."""
    today = today or today_in_nepal()
    queued = 0
    for gym in db.scalars(select(Gym).where(Gym.status == GYM_ACTIVE)):
        queued += _run_gym(db, gym, today)
    return queued


def _offset(rule: ReminderRule) -> int:
    """Days from the chain's end: a lapsed rule's 30 is the same as expiry's +30."""
    return rule.days


def _reachable(gym: Gym):
    """Members an automation may text: on the books, with the app, not erased."""
    return (
        Member.gym_id == gym.id,
        Member.is_archived.is_(False),
        Member.app_access.is_(True),
        Member.erased_at.is_(None),
    )


def _send(
    db: Session,
    gym: Gym,
    rule: ReminderRule,
    member: Member,
    key: str,
    body: str,
    *,
    pushable: set[uuid.UUID],
    membership_id: uuid.UUID | None = None,
    quiet: bool = False,
) -> bool:
    """Record the occasion, then send it: by push if the member's phone takes
    it, else SMS (§16.3, 8.3). False if it was sent before.

    `quiet` records it without sending: an older rule overtaken by a newer one.
    """
    inserted = db.execute(
        insert(ReminderLog)
        .values(
            id=uuid.uuid4(),
            gym_id=gym.id,
            rule_id=rule.id,
            dedupe_key=key,
            member_id=member.id,
            membership_id=membership_id,
        )
        .on_conflict_do_nothing()
        .returning(ReminderLog.id)
    ).scalar()
    if not inserted or quiet:
        return False
    _, message = push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=body,
        url=f"/{gym.slug}{TAP_OPENS[rule.trigger]}",
        tag=f"{rule.trigger}:{rule.id}",
        sms_body=body,
        sms_kind=SMS_REMINDER,
        pushable=pushable,
    )
    if message is not None:
        db.execute(
            ReminderLog.__table__.update()
            .where(ReminderLog.id == inserted)
            .values(sms_message_id=message.id)
        )
    return True


# Where tapping each automation's notification opens in the member app.
TAP_OPENS = {
    TRIGGER_EXPIRY: "/renew",
    TRIGGER_LAPSED: "/renew",
    TRIGGER_DUES: "/payments",
    TRIGGER_NOT_VISITING: "",
    TRIGGER_BIRTHDAY: "",
}


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
    by_trigger: dict[str, list[ReminderRule]] = defaultdict(list)
    for rule in rules:
        by_trigger[rule.trigger].append(rule)
    pushable = push.reachable_in_gym(db, gym.id)
    return (
        _chain_ends(
            db,
            gym,
            today,
            by_trigger[TRIGGER_EXPIRY] + by_trigger[TRIGGER_LAPSED],
            pushable,
        )
        + _dues(db, gym, today, by_trigger[TRIGGER_DUES], pushable)
        + _not_visiting(db, gym, today, by_trigger[TRIGGER_NOT_VISITING], pushable)
        + _birthdays(db, gym, today, by_trigger[TRIGGER_BIRTHDAY], pushable)
    )


def _chain_ends(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """Expiry and win-back: both count days from the end of the chain."""
    if not rules:
        return 0
    # Every rule looks at chain ends within [today - d - CATCH_UP, today - d].
    earliest = min(today - dt.timedelta(days=_offset(r) + CATCH_UP_DAYS) for r in rules)
    latest = max(today - dt.timedelta(days=_offset(r)) for r in rules)
    candidates = list(
        db.scalars(
            select(Member)
            .join(Membership, Membership.member_id == Member.id)
            .where(
                *_reachable(gym),
                Membership.cancelled_at.is_(None),
                Membership.end_date >= earliest,
                Membership.end_date <= latest,
            )
            .distinct()
        )
    )
    states = members_service.states_for(db, candidates, today)

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
            target = end + dt.timedelta(days=_offset(rule))
            if not (target <= today <= target + dt.timedelta(days=CATCH_UP_DAYS)):
                continue
            # Several rules due at once (a missed day): send only the latest.
            overtaken = any(
                _offset(r) > _offset(rule)
                and end + dt.timedelta(days=_offset(r)) <= today
                for r in rules
            )
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"membership:{last.id}",
                render(rule.template, values_for(gym, member, last, end)),
                pushable=pushable,
                membership_id=last.id,
                quiet=overtaken,
            )
    return queued


def _dues(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """Still owed `days` after the sale: one SMS per rule and membership."""
    queued = 0
    for rule in rules:
        sold_from = dt.datetime.combine(
            today - dt.timedelta(days=rule.days + CATCH_UP_DAYS), dt.time(), NEPAL
        )
        sold_to = dt.datetime.combine(
            today - dt.timedelta(days=rule.days - 1), dt.time(), NEPAL
        )
        rows = db.execute(
            select(Membership, Member)
            .join(Member, Member.id == Membership.member_id)
            .where(
                *_reachable(gym),
                Membership.cancelled_at.is_(None),
                Membership.created_at >= sold_from,
                Membership.created_at < sold_to,
            )
        ).all()
        payments: dict[uuid.UUID, list] = defaultdict(list)
        for p in ms.payments_for(db, [row.Membership.id for row in rows]):
            payments[p.membership_id].append(p)  # type: ignore[index]
        for membership, member in rows:
            owed = ms.dues_of(membership, payments[membership.id])
            if owed <= 0:
                continue
            values = values_for(
                gym, member, membership, membership.end_date, amount=rupees(owed)
            )
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"membership:{membership.id}",
                render(rule.template, values),
                pushable=pushable,
                membership_id=membership.id,
            )
    return queued


def _not_visiting(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """Active, no visit for `days`: once per spell away (the key holds the
    last visit's date), and only near the day the spell crossed `days`."""
    queued = 0
    for rule in rules:
        members = list(
            db.scalars(
                select(Member).where(
                    *_reachable(gym),
                    members_service.not_visiting_filter(today, rule.days),
                )
            )
        )
        visits = members_service.last_visits(db, [m.id for m in members])
        states = members_service.states_for(db, members, today)
        for member in members:
            last = visits.get(member.id)
            since = (last or member.created_at).astimezone(NEPAL).date()
            away = (today - since).days
            if away > rule.days + CATCH_UP_DAYS:
                continue  # away long before the rule was switched on
            state = states[member.id]
            values = values_for(
                gym, member, state.current, state.valid_until, days=away
            )
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"visit:{member.id}:{since.isoformat() if last else 'never'}",
                render(rule.template, values),
                pushable=pushable,
            )
    return queued


def _birthdays(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """On the day, to current members (active or frozen) only."""
    if not rules:
        return 0
    # Today, or a day the worker missed: the day each (month, day) fell on.
    days: dict[tuple[int, int], dt.date] = {}
    for n in range(CATCH_UP_DAYS, -1, -1):
        day = today - dt.timedelta(days=n)
        days[(day.month, day.day)] = day
        if (day.month, day.day) == (2, 28) and not calendar.isleap(day.year):
            days[(2, 29)] = day  # born on 29 February: the 28th in other years
    members = list(
        db.scalars(
            select(Member).where(
                *_reachable(gym),
                tuple_(
                    extract("month", Member.date_of_birth),
                    extract("day", Member.date_of_birth),
                ).in_(list(days)),
                or_(
                    members_service.status_filter(ms.ACTIVE, today),
                    members_service.status_filter(ms.FROZEN, today),
                ),
            )
        )
    )
    queued = 0
    for member in members:
        assert member.date_of_birth is not None
        day = days[(member.date_of_birth.month, member.date_of_birth.day)]
        for rule in rules:
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"birthday:{member.id}:{day.year}",
                render(rule.template, values_for(gym, member, None, None)),
                pushable=pushable,
            )
    return queued


def handle_daily(db: Session, payload: dict) -> None:
    run_daily(
        db, dt.date.fromisoformat(payload["date"]) if payload.get("date") else None
    )
