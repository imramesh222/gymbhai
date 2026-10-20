"""Automations and the SMS members get at the desk (PLAN.md §5.3, §9, §16.3 8.2).

Automations run daily at 09:00 Nepal time. Each enabled rule has a trigger:

- expiry: the membership chain ends `days` away ("7 days before", "on the
  day"). Measured from the END OF THE CHAIN, so someone who has already
  renewed is never told they are about to expire.
- lapsed: the chain ended `days` ago and they haven't renewed (win-back).
- dues: money still owed on a membership `days` after it was sold.
- not_visiting: active, and no visit for `days` days.
- birthday: on the member's birthday.
- pt_ending: personal training ends `days` away, counted like expiry from the
  end of the member's last package; a pack used up early ends on the day of
  its last session (§18.3).
- pt_dues: money still owed on personal training `days` after it was sold.
- progress: `days` after their last progress check (§19.5). By push only,
  free: a nudge isn't worth an SMS credit, so only members whose phone takes
  push are reminded.

Nothing is sent twice: reminder_log holds one row per rule and occasion (its
`dedupe_key`). A day the worker missed is caught up for up to CATCH_UP_DAYS;
{days} in the text is always the true number.
"""

import calendar
import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import extract, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import sms_defaults
from app.core.calendar import format_date
from app.core.config import settings
from app.core.sms_text import render
from app.core.time import NEPAL, today_in_nepal
from app.core.whatsapp_templates import WhatsApp, for_rule
from app.models.gym import GYM_ACTIVE, Gym
from app.models.member import Member
from app.models.membership import Membership, MembershipGroup
from app.models.messaging import (
    SMS_MEMBERSHIP,
    SMS_REMINDER,
    SMS_WELCOME,
    TRIGGER_BIRTHDAY,
    TRIGGER_DUES,
    TRIGGER_EXPIRY,
    TRIGGER_LAPSED,
    TRIGGER_NOT_VISITING,
    TRIGGER_PROGRESS,
    TRIGGER_PT_DUES,
    TRIGGER_PT_ENDING,
    ReminderLog,
    ReminderRule,
)
from app.models.progress import ProgressEntry
from app.models.staff import StaffUser
from app.models.training import PtPackage
from app.services import members as members_service
from app.services import memberships as ms
from app.services import training
from app.services.push import service as push

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


def pt_values(
    gym: Gym,
    member: Member,
    package: PtPackage | None,
    end: dt.date | None,
    trainer: str | None,
    **extra: object,
) -> dict[str, object]:
    """As values_for, with {plan} the PT plan and {trainer} the trainer's
    first name (§18.3)."""
    return values_for(
        gym,
        member,
        None,
        end,
        plan=package.plan_name if package else "",
        trainer=trainer.split()[0] if trainer else "",
        **extra,
    )


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
    sms_allowed: bool = True,
) -> None:
    """The SMS from §5.3 step 5: welcome for a new member, else "active until".

    On a family or couple plan, `membership` is the payer's: the others on it
    hear by push only (§19.1), as one SMS per family is enough."""
    if membership.group_id is not None and sms_allowed:
        for other in ms.group_memberships(db, membership.group_id):
            if other.member_id == member.id or other.cancelled_at is not None:
                continue
            person = db.get(Member, other.member_id)
            if person is not None:
                after_sale(
                    db,
                    gym,
                    person,
                    other,
                    new_member=False,
                    staff_id=staff_id,
                    sms_allowed=False,
                )
    if not member.app_access:
        return
    state = members_service.state(db, member)
    end = state.valid_until or membership.end_date
    template = gym.config.welcome_sms if new_member else gym.config.membership_sms
    values = values_for(gym, member, membership, end)
    body = render(template, values)
    if new_member:
        # The welcome carries the app's link: it goes before they can have
        # push. By WhatsApp if they agreed (§19.3), else SMS.
        push.paid_message(
            db,
            gym,
            member,
            sms_body=body,
            sms_kind=SMS_WELCOME,
            whatsapp=WhatsApp("welcome", values, button=gym.slug),
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
        sms_allowed=sms_allowed,
        whatsapp=WhatsApp("membership_active", values, button=gym.slug),
    )


def welcome_text(gym: Gym, member: Member, state: members_service.MemberState) -> str:
    if not state.current:
        return render(
            sms_defaults.WELCOME_NO_PLAN[gym.config.language],
            values_for(gym, member, None, None),
        )
    return render(
        gym.config.welcome_sms,
        values_for(gym, member, state.current, state.valid_until),
    )


def welcome(db: Session, gym: Gym, member: Member, staff_id: uuid.UUID | None) -> None:
    """For a member added without a membership, or "Resend welcome" (§5.5):
    by WhatsApp if they agreed (§19.3), else SMS."""
    state = members_service.state(db, member)
    template = "welcome" if state.current else "welcome_no_plan"
    push.paid_message(
        db,
        gym,
        member,
        sms_body=welcome_text(gym, member, state),
        sms_kind=SMS_WELCOME,
        whatsapp=WhatsApp(
            template,
            values_for(gym, member, state.current, state.valid_until),
            button=gym.slug,
        ),
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


# Messages staff send from their own phone, on WhatsApp (§18.5).
MESSAGE_PURPOSES = ("reminder", "dues", "not_visiting", "welcome", "pt_dues")


def _wording(db: Session, gym: Gym, trigger: str) -> str:
    """The gym's wording for an automation (its first rule), else the default."""
    rule = db.scalars(
        select(ReminderRule)
        .where(ReminderRule.gym_id == gym.id, ReminderRule.trigger == trigger)
        .order_by(ReminderRule.days)
    ).first()
    if rule:
        return rule.template
    return next(
        text
        for kind, _, text, _ in sms_defaults.RULES[gym.config.language]
        if kind == trigger
    )


def pt_dues_text(db: Session, gym: Gym, member: Member) -> str:
    """What they owe on personal training, in the gym's PT dues wording."""
    packages = [p for p in training.of_member(db, member) if p.cancelled_at is None]
    paid = training.payments_by_package(db, [p.id for p in packages])
    owed = {p.id: training.dues_of(p, paid[p.id]) for p in packages}
    package = max(packages, key=lambda p: (owed[p.id], p.start_date), default=None)
    trainer = db.get(StaffUser, package.trainer_id) if package else None
    values = pt_values(
        gym,
        member,
        package,
        package.end_date if package else None,
        trainer.name if trainer else None,
        amount=rupees(sum(max(amount, 0) for amount in owed.values())),
    )
    return render(_wording(db, gym, TRIGGER_PT_DUES), values)


def message_text(db: Session, gym: Gym, member: Member, purpose: str) -> str:
    """The gym's own wording, as its SMS or automation would say it now."""
    if purpose == "reminder":
        return reminder_text(db, gym, member)
    if purpose == "pt_dues":
        return pt_dues_text(db, gym, member)
    state = members_service.state(db, member)
    if purpose == "welcome":
        return welcome_text(gym, member, state)
    template = _wording(
        db, gym, TRIGGER_DUES if purpose == "dues" else TRIGGER_NOT_VISITING
    )
    if purpose == "dues":
        extra = {"amount": rupees(state.dues)}
    else:
        last = members_service.last_visits(db, [member.id]).get(member.id)
        since = (last or member.created_at).astimezone(NEPAL).date()
        extra = {"days": (today_in_nepal() - since).days}
    return render(
        template, values_for(gym, member, state.current, state.valid_until, **extra)
    )


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
    values: dict[str, object],
    *,
    pushable: set[uuid.UUID],
    membership_id: uuid.UUID | None = None,
    quiet: bool = False,
    sms_allowed: bool = True,
) -> bool:
    """Record the occasion, then send it: by push if the member's phone takes
    it, else WhatsApp where the rule has a template (§19.3), else SMS (§16.3,
    8.3). False if it was sent before.

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
    body = render(rule.template, values)
    template = for_rule(rule.trigger, rule.days)
    path = f"{gym.slug}{TAP_OPENS[rule.trigger]}"
    _, message = push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=body,
        url=f"/{path}",
        tag=f"{rule.trigger}:{rule.id}",
        sms_body=body,
        sms_kind=SMS_REMINDER,
        pushable=pushable,
        sms_allowed=sms_allowed,
        whatsapp=WhatsApp(template.key, values, button=path) if template else None,
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
    # Home shows their personal training, and what they owe on it.
    TRIGGER_PT_ENDING: "",
    TRIGGER_PT_DUES: "",
    TRIGGER_PROGRESS: "/progress",
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
        + _pt_ending(db, gym, today, by_trigger[TRIGGER_PT_ENDING], pushable)
        + _pt_dues(db, gym, today, by_trigger[TRIGGER_PT_DUES], pushable)
        + _progress(db, gym, today, by_trigger[TRIGGER_PROGRESS], pushable)
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
    payers = _payers(db, {m.group_id for st in states.values() for m in st.memberships})

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
        # A family or couple plan is renewed by whoever pays: only they're
        # reminded, not everyone on the same phone (§19.1).
        if payers.get(last.group_id, member.id) != member.id:
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
                values_for(gym, member, last, end),
                pushable=pushable,
                membership_id=last.id,
                quiet=overtaken,
            )
    return queued


def _payers(
    db: Session, group_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID | None, uuid.UUID]:
    """Who pays for each family or couple plan; no query without one."""
    wanted = {g for g in group_ids if g is not None}
    if not wanted:
        return {}
    return dict(
        db.execute(
            select(MembershipGroup.id, MembershipGroup.payer_member_id).where(
                MembershipGroup.id.in_(wanted)
            )
        ).all()
    )


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
                values,
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
                values,
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
                values_for(gym, member, None, None),
                pushable=pushable,
            )
    return queued


def _trainer_names(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = set(ids)
    if not ids:
        return {}
    return {
        row.id: row.name
        for row in db.execute(
            select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(ids))
        )
    }


def _pt_ending(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """Before, on or after the day a member's personal training ends (§18.3):
    counted from their last package, so someone who has bought more isn't
    told. A pack used up early ends on the day of its last session."""
    if not rules:
        return 0
    earliest = min(today - dt.timedelta(days=r.days + CATCH_UP_DAYS) for r in rules)
    latest = max(today - dt.timedelta(days=r.days) for r in rules)
    # Who has a package that may end in the window (a pack used up early
    # ends before its end date, never after), and all their packages: a
    # later one means they have renewed.
    ending = select(PtPackage.member_id).where(
        PtPackage.gym_id == gym.id,
        PtPackage.cancelled_at.is_(None),
        PtPackage.end_date >= earliest,
        PtPackage.start_date <= latest,
    )
    rows = db.execute(
        select(PtPackage, Member)
        .join(Member, Member.id == PtPackage.member_id)
        .where(
            *_reachable(gym),
            PtPackage.gym_id == gym.id,
            PtPackage.cancelled_at.is_(None),
            PtPackage.member_id.in_(ending),
        )
    ).all()
    end_of = training.ends(db, [row.PtPackage for row in rows])
    last: dict[uuid.UUID, tuple[PtPackage, Member]] = {}
    for package, member in rows:
        held = last.get(member.id)
        if held is None or (end_of[package.id], package.start_date) > (
            end_of[held[0].id],
            held[0].start_date,
        ):
            last[member.id] = (package, member)
    trainers = _trainer_names(db, (p.trainer_id for p, _ in last.values()))

    queued = 0
    for package, member in last.values():
        end = end_of[package.id]
        for rule in rules:
            target = end + dt.timedelta(days=rule.days)
            if not (target <= today <= target + dt.timedelta(days=CATCH_UP_DAYS)):
                continue
            # Several rules due at once (a missed day): send only the latest.
            overtaken = any(
                r.days > rule.days and end + dt.timedelta(days=r.days) <= today
                for r in rules
            )
            values = pt_values(
                gym, member, package, end, trainers.get(package.trainer_id)
            )
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"pt:{package.id}",
                values,
                pushable=pushable,
                quiet=overtaken,
            )
    return queued


def _pt_dues(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """Still owed on personal training `days` after the sale: one message per
    rule and package."""
    queued = 0
    for rule in rules:
        sold_from = dt.datetime.combine(
            today - dt.timedelta(days=rule.days + CATCH_UP_DAYS), dt.time(), NEPAL
        )
        sold_to = dt.datetime.combine(
            today - dt.timedelta(days=rule.days - 1), dt.time(), NEPAL
        )
        rows = db.execute(
            select(PtPackage, Member)
            .join(Member, Member.id == PtPackage.member_id)
            .where(
                *_reachable(gym),
                PtPackage.gym_id == gym.id,
                PtPackage.cancelled_at.is_(None),
                PtPackage.created_at >= sold_from,
                PtPackage.created_at < sold_to,
            )
        ).all()
        paid = training.payments_by_package(db, [row.PtPackage.id for row in rows])
        trainers = _trainer_names(db, (row.PtPackage.trainer_id for row in rows))
        for package, member in rows:
            owed = training.dues_of(package, paid[package.id])
            if owed <= 0:
                continue
            values = pt_values(
                gym,
                member,
                package,
                package.end_date,
                trainers.get(package.trainer_id),
                amount=rupees(owed),
            )
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"pt:{package.id}",
                values,
                pushable=pushable,
            )
    return queued


def _progress(
    db: Session,
    gym: Gym,
    today: dt.date,
    rules: list[ReminderRule],
    pushable: set[uuid.UUID],
) -> int:
    """`days` after their last check, by push only (§19.5): once per check
    (the key holds its date), and only near the day it came due."""
    if not rules or not pushable:
        return 0
    last = (
        select(ProgressEntry.member_id, func.max(ProgressEntry.measured_on).label("on"))
        .where(ProgressEntry.gym_id == gym.id)
        .group_by(ProgressEntry.member_id)
        .subquery()
    )
    queued = 0
    for rule in rules:
        latest = today - dt.timedelta(days=rule.days)
        rows = db.execute(
            select(Member, last.c.on)
            .join(last, last.c.member_id == Member.id)
            .where(
                *_reachable(gym),
                Member.id.in_(pushable),
                last.c.on <= latest,
                last.c.on >= latest - dt.timedelta(days=CATCH_UP_DAYS),
            )
        ).all()
        for member, on in rows:
            values = values_for(gym, member, None, None, days=(today - on).days)
            queued += _send(
                db,
                gym,
                rule,
                member,
                f"progress:{member.id}:{on.isoformat()}",
                values,
                pushable=pushable,
                sms_allowed=False,
            )
    return queued


def handle_daily(db: Session, payload: dict) -> None:
    run_daily(
        db, dt.date.fromisoformat(payload["date"]) if payload.get("date") else None
    )
