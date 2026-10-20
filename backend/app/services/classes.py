"""Group classes (PLAN.md §19.4): the timetable, each class, booking with
places counted and a waitlist, and who came.

* The worker makes each slot's classes AHEAD_DAYS ahead, once each; changing
  the timetable changes only the classes nobody has booked yet.
* A booking is a place, or a spot in the queue when the class is full. The
  class is locked while places are counted, so two people can't both take the
  last one. A place given back goes to the first in the queue, who is told by
  push, until WAITLIST_STOPS before the start.
* Who may book: a membership covering the class's day, at its branch, whose
  plan includes that class (none, all, or the chosen types; copied at sale).
* Who came: the instructor's tick, or else a check-in at the door from an
  hour before the class to its end. A booking never counts as a visit itself.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core import class_text
from app.core.calendar import format_date
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.activity import ACTOR_SYSTEM
from app.models.classes import (
    BOOKED,
    CANCELLED,
    CLASSES_ALL,
    CLASSES_NONE,
    SOURCE_APP,
    WAITLIST,
    ClassBooking,
    ClassSlot,
    ClassType,
    GymClass,
)
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn
from app.models.messaging import SMS_NOTICE
from app.models.plan import Plan
from app.models.staff import StaffUser
from app.services import activity, live
from app.services import members as members_service
from app.services import memberships as ms
from app.services.push import service as push

AHEAD_DAYS = 28
WAITLIST_STOPS = dt.timedelta(hours=2)
REMINDER_BEFORE = dt.timedelta(hours=1)
# Checked in at the door this long before a class: they came to it.
CAME_BEFORE = dt.timedelta(hours=1)
NO_SHOW_DAYS = 30

JOB_GENERATE = "classes.generate"
JOB_REMINDER = "classes.reminder"


def starts_at(day: dt.date, starts: str) -> dt.datetime:
    hour, minute = map(int, starts.split(":"))
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=NEPAL)


def local_day(moment: dt.datetime) -> dt.date:
    return moment.astimezone(NEPAL).date()


# --- instructors ----------------------------------------------------------------


def instructors(db: Session, gym_id: uuid.UUID) -> list[StaffUser]:
    """Who may teach: staff who teach classes, and the owner."""
    return list(
        db.scalars(
            select(StaffUser)
            .where(
                StaffUser.gym_id == gym_id,
                StaffUser.is_active,
                or_(
                    StaffUser.is_owner,
                    StaffUser.permissions.contains([Permission.CLASSES_TEACH.value]),
                ),
            )
            .order_by(StaffUser.is_owner.desc(), StaffUser.name)
        )
    )


def check_instructor(
    db: Session, gym_id: uuid.UUID, staff_id: uuid.UUID | None
) -> None:
    if staff_id is None:
        return
    if not any(s.id == staff_id for s in instructors(db, gym_id)):
        raise AppError(
            422,
            "bad_instructor",
            "Choose one of the gym's instructors: staff who teach classes.",
        )


# --- the timetable makes the classes -----------------------------------------------


def generate(
    db: Session,
    *,
    gym_id: uuid.UUID | None = None,
    slot_id: uuid.UUID | None = None,
    today: dt.date | None = None,
) -> int:
    """Each active slot's classes for the next AHEAD_DAYS days, made once.
    Returns how many were new."""
    today = today or today_in_nepal()
    stmt = (
        select(ClassSlot, ClassType)
        .join(ClassType, ClassType.id == ClassSlot.type_id)
        .where(ClassSlot.is_active, ClassType.is_active)
    )
    if gym_id is not None:
        stmt = stmt.where(ClassSlot.gym_id == gym_id)
    if slot_id is not None:
        stmt = stmt.where(ClassSlot.id == slot_id)
    now = utcnow()
    made = 0
    for slot, _ in db.execute(stmt).all():
        for offset in range(AHEAD_DAYS):
            day = today + dt.timedelta(days=offset)
            if day.weekday() != slot.weekday:
                continue
            start = starts_at(day, slot.starts)
            if start <= now:
                continue
            inserted = db.execute(
                insert(GymClass)
                .values(
                    id=uuid.uuid4(),
                    gym_id=slot.gym_id,
                    branch_id=slot.branch_id,
                    type_id=slot.type_id,
                    slot_id=slot.id,
                    starts_at=start,
                    ends_at=start + dt.timedelta(minutes=slot.minutes),
                    instructor_id=slot.instructor_id,
                    places=slot.places,
                )
                .on_conflict_do_nothing(constraint="uq_classes_slot_start")
                .returning(GymClass.id)
            ).first()
            made += inserted is not None
    return made


def _live_bookings():
    return ClassBooking.status != CANCELLED


def _unbooked_future(slot_id: uuid.UUID):
    """A slot's classes still to come that nobody has booked."""
    return select(GymClass).where(
        GymClass.slot_id == slot_id,
        GymClass.starts_at > utcnow(),
        GymClass.cancelled_at.is_(None),
        ~exists().where(ClassBooking.class_id == GymClass.id, _live_bookings()),
    )


def sync_slot(db: Session, slot: ClassSlot) -> None:
    """After the timetable changed: its unbooked classes follow it (or go, if
    the slot was taken off), and any new ones are made."""
    for gym_class in db.scalars(_unbooked_future(slot.id)):
        if not slot.is_active:
            db.delete(gym_class)
            continue
        day = local_day(gym_class.starts_at)
        if day.weekday() != slot.weekday:
            db.delete(gym_class)  # moved to another day: made again below
            continue
        start = starts_at(day, slot.starts)
        gym_class.starts_at = start
        gym_class.ends_at = start + dt.timedelta(minutes=slot.minutes)
        gym_class.type_id = slot.type_id
        gym_class.instructor_id = slot.instructor_id
        gym_class.places = slot.places
    db.flush()
    if slot.is_active:
        generate(db, slot_id=slot.id)
    live.publish(db, gym_id=slot.gym_id, kind=live.CLASS, branch_id=slot.branch_id)


def handle_generate(db: Session, payload: dict) -> None:
    generate(db)


# --- who may book --------------------------------------------------------------


@dataclass
class Counts:
    booked: int = 0
    waiting: int = 0


def counts(db: Session, class_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Counts]:
    """Places taken and the queue, for many classes in one query."""
    found: dict[uuid.UUID, Counts] = defaultdict(Counts)
    if not class_ids:
        return found
    rows = db.execute(
        select(ClassBooking.class_id, ClassBooking.status, func.count())
        .where(ClassBooking.class_id.in_(class_ids), _live_bookings())
        .group_by(ClassBooking.class_id, ClassBooking.status)
    ).all()
    for class_id, status, n in rows:
        if status == BOOKED:
            found[class_id].booked = n
        else:
            found[class_id].waiting = n
    return found


def _came_at_door():
    """Let in at the class's branch from CAME_BEFORE its start to its end."""
    return exists().where(
        CheckIn.member_id == ClassBooking.member_id,
        CheckIn.branch_id == GymClass.branch_id,
        CheckIn.result.in_(LET_IN),
        CheckIn.at >= GymClass.starts_at - CAME_BEFORE,
        CheckIn.at <= GymClass.ends_at,
    )


def no_shows(db: Session, member_id: uuid.UUID, now: dt.datetime | None = None) -> int:
    """Booked, didn't come, in the last NO_SHOW_DAYS: not ticked, and no
    check-in at the door for it either."""
    now = now or utcnow()
    return (
        db.scalar(
            select(func.count())
            .select_from(ClassBooking)
            .join(GymClass, GymClass.id == ClassBooking.class_id)
            .where(
                ClassBooking.member_id == member_id,
                ClassBooking.status == BOOKED,
                GymClass.cancelled_at.is_(None),
                GymClass.ends_at < now,
                GymClass.ends_at >= now - dt.timedelta(days=NO_SHOW_DAYS),
                or_(
                    ClassBooking.attended.is_(False),
                    and_(ClassBooking.attended.is_(None), ~_came_at_door()),
                ),
            )
        )
        or 0
    )


def why_not(
    db: Session, gym: Gym, member: Member, gym_class: GymClass
) -> tuple[str, str] | None:
    """Why this member may not book this class, as (code, message); None if
    they may."""
    if member.is_archived:
        return "member_archived", "Restore this member first."
    day = local_day(gym_class.starts_at)
    state = members_service.state_inputs(db, [member]).state(member.id, day)
    if state.status == ms.FROZEN:
        return "frozen", "The membership is frozen on that day."
    current = state.current
    if state.status != ms.ACTIVE or current is None or state.used_up_today:
        return "no_membership", "No membership covers that day."
    if current.classes == CLASSES_NONE or (
        current.classes != CLASSES_ALL
        and str(gym_class.type_id) not in (current.class_type_ids or [])
    ):
        return "plan_no_class", "Their plan doesn't include this class."
    plan = db.get(Plan, current.plan_id) if current.plan_id else None
    if plan is not None and not ms.plan_covers_branch(db, plan, gym_class.branch_id):
        return "branch", "Their plan isn't for this class's branch."
    config = gym.config
    if config.no_show_limit and no_shows(db, member.id) >= config.no_show_limit:
        return (
            "no_shows",
            f"Booked and didn't come {config.no_show_limit} times in "
            f"{NO_SHOW_DAYS} days: booking is paused for "
            f"{config.no_show_block_days} days.",
        )
    return None


# --- booking ---------------------------------------------------------------------


def lock(db: Session, gym_class: GymClass) -> None:
    """While places are counted: two at once must not both take the last."""
    db.refresh(gym_class, with_for_update=True)


def _type_name(db: Session, gym_class: GymClass) -> str:
    kind = db.get(ClassType, gym_class.type_id)
    return kind.name if kind else ""


def _remind(db: Session, booking: ClassBooking, gym_class: GymClass) -> None:
    from app.worker import enqueue

    at = gym_class.starts_at - REMINDER_BEFORE
    if at > utcnow():
        enqueue(db, JOB_REMINDER, {"booking_id": str(booking.id)}, run_at=at)


def book(
    db: Session,
    gym: Gym,
    member: Member,
    gym_class: GymClass,
    *,
    staff: StaffUser | None = None,
) -> ClassBooking:
    """A place, or the waitlist when it's full. From the app (`staff` None)
    inside the gym's booking window; at the desk until the class starts.
    `gym_class` is locked here."""
    lock(db, gym_class)
    now = utcnow()
    config = gym.config
    if gym_class.cancelled_at is not None:
        raise AppError(409, "class_cancelled", "This class is cancelled.")
    if gym_class.starts_at <= now:
        raise AppError(409, "class_started", "This class has started.")
    if staff is None:
        if gym_class.starts_at - dt.timedelta(days=config.class_booking_days) > now:
            raise AppError(
                409,
                "booking_not_open",
                f"Booking opens {config.class_booking_days} days before.",
            )
        if (
            gym_class.starts_at - dt.timedelta(minutes=config.class_closes_minutes)
            < now
        ):
            raise AppError(409, "booking_closed", "Booking for this class has closed.")
    already = db.scalar(
        select(ClassBooking.id).where(
            ClassBooking.class_id == gym_class.id,
            ClassBooking.member_id == member.id,
            _live_bookings(),
        )
    )
    if already:
        raise AppError(409, "already_booked", "Already booked for this class.")
    refused = why_not(db, gym, member, gym_class)
    if refused:
        raise AppError(409, refused[0], refused[1])

    taken = counts(db, [gym_class.id])[gym_class.id].booked
    booking = ClassBooking(
        gym_id=gym.id,
        class_id=gym_class.id,
        member_id=member.id,
        status=BOOKED if taken < gym_class.places else WAITLIST,
        booked_at=now,
        source=SOURCE_APP if staff is None else "desk",
        booked_by=staff.id if staff else None,
    )
    db.add(booking)
    db.flush()
    _log(db, booking, "class_booking.created", staff=staff, member=member)
    if booking.status == BOOKED:
        _remind(db, booking, gym_class)
    _changed(db, gym_class, member.id)
    return booking


def cancel_booking(
    db: Session,
    gym: Gym,
    booking: ClassBooking,
    gym_class: GymClass,
    *,
    staff: StaffUser | None = None,
) -> ClassBooking:
    """Give a place back (or leave the queue). After the gym's cut-off it's
    a late cancel. The place goes to the first in the queue."""
    lock(db, gym_class)
    if booking.status == CANCELLED:
        raise AppError(409, "booking_cancelled", "This booking is already cancelled.")
    now = utcnow()
    if gym_class.starts_at <= now:
        raise AppError(409, "class_started", "This class has started.")
    held_place = booking.status == BOOKED
    booking.status = CANCELLED
    booking.cancelled_at = now
    cutoff = gym_class.starts_at - dt.timedelta(hours=gym.config.class_cancel_hours)
    booking.late = held_place and now > cutoff
    db.flush()  # the session doesn't autoflush: counts after this must see it
    member = db.get(Member, booking.member_id)
    _log(db, booking, "class_booking.cancelled", staff=staff, member=member)
    if held_place:
        promote(db, gym, gym_class)
    _changed(db, gym_class, booking.member_id)
    return booking


def promote(db: Session, gym: Gym, gym_class: GymClass) -> ClassBooking | None:
    """A place came free: the first in the queue gets it, and hears so."""
    if gym_class.starts_at - WAITLIST_STOPS < utcnow():
        return None
    db.flush()  # the place given back, before counting
    if counts(db, [gym_class.id])[gym_class.id].booked >= gym_class.places:
        return None
    first = db.scalars(
        select(ClassBooking)
        .where(ClassBooking.class_id == gym_class.id, ClassBooking.status == WAITLIST)
        .order_by(ClassBooking.booked_at, ClassBooking.id)
        .limit(1)
    ).first()
    if first is None:
        return None
    first.status = BOOKED
    member = db.get(Member, first.member_id)
    assert member is not None
    _log(db, first, "class_booking.promoted", member=None, staff=None)
    _remind(db, first, gym_class)
    _tell(
        db,
        gym,
        member,
        class_text.PROMOTED,
        gym_class,
        url=f"/{gym.slug}/classes",
    )
    live.member_changed(db, gym.id, member.id, gym_class.branch_id)
    return first


def cancel_class(
    db: Session,
    ctx: StaffContext,
    gym_class: GymClass,
    reason: str,
    *,
    sms: bool = False,
) -> GymClass:
    """Everyone booked or waiting hears it: by push, and by SMS where the
    gym asked for it and push can't reach."""
    lock(db, gym_class)
    if gym_class.cancelled_at is not None:
        raise AppError(409, "class_cancelled", "This class is already cancelled.")
    if gym_class.ends_at <= utcnow():
        raise AppError(409, "class_over", "This class is over.")
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    gym_class.cancelled_at = utcnow()
    gym_class.cancel_reason = reason
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "class.cancelled",
        entity="class",
        entity_id=gym_class.id,
        reason=reason,
    )
    for booking in db.scalars(
        select(ClassBooking).where(
            ClassBooking.class_id == gym_class.id, _live_bookings()
        )
    ):
        member = db.get(Member, booking.member_id)
        if member is not None:
            _tell(
                db,
                gym,
                member,
                class_text.CANCELLED,
                gym_class,
                url=f"/{gym.slug}/classes",
                reason=reason,
                sms=sms,
            )
    _changed(db, gym_class, None)
    return gym_class


def set_attended(
    db: Session,
    ctx: StaffContext,
    booking: ClassBooking,
    gym_class: GymClass,
    came: bool,
) -> ClassBooking:
    """The instructor's tick: their own classes, or anyone's for staff who
    book or manage classes."""
    if not (
        ctx.can(Permission.CLASSES_MANAGE)
        or ctx.can(Permission.CLASSES_BOOK)
        or gym_class.instructor_id == ctx.staff.id
    ):
        raise AppError(
            403,
            "not_your_class",
            "Only its instructor, or the desk, marks who came.",
        )
    if booking.status != BOOKED:
        raise AppError(409, "not_booked", "Only a booked place can be marked.")
    if gym_class.starts_at - CAME_BEFORE > utcnow():
        raise AppError(409, "class_not_started", "The class hasn't started yet.")
    before = booking.attended
    booking.attended = came
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "class_booking.attended",
        entity="class_booking",
        entity_id=booking.id,
        changes={"attended": {"before": before, "after": came}},
    )
    _changed(db, gym_class, booking.member_id)
    return booking


def came_at_door(
    db: Session, bookings: Iterable[tuple[ClassBooking, GymClass]]
) -> set[uuid.UUID]:
    """Which of these bookings' members checked in at the door for them."""
    pairs = list(bookings)
    if not pairs:
        return set()
    ids = [b.id for b, _ in pairs]
    return set(
        db.scalars(
            select(ClassBooking.id)
            .join(GymClass, GymClass.id == ClassBooking.class_id)
            .where(ClassBooking.id.in_(ids), _came_at_door())
        )
    )


# --- telling people -------------------------------------------------------------


def _when(gym: Gym, gym_class: GymClass) -> tuple[str, str]:
    local = gym_class.starts_at.astimezone(NEPAL)
    return format_date(local.date(), gym.config.date_display), local.strftime("%H:%M")


def _tell(
    db: Session,
    gym: Gym,
    member: Member,
    wording: dict[str, str],
    gym_class: GymClass,
    *,
    url: str,
    reason: str = "",
    sms: bool = False,
) -> None:
    language = member.language or gym.config.language
    day, time = _when(gym, gym_class)
    values = {
        "class": _type_name(db, gym_class),
        "day": day,
        "time": time,
        "reason": reason,
    }
    text = wording.get(language, wording["en"]).format(**values).strip()
    push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=text,
        url=url,
        tag=f"class:{gym_class.id}",
        sms_body=f"{gym.name}: {text}",
        sms_kind=SMS_NOTICE,
        sms_allowed=sms,
    )


def handle_reminder(db: Session, payload: dict) -> None:
    """An hour before: still booked, class still on, by push only (free)."""
    booking = db.get(ClassBooking, uuid.UUID(payload["booking_id"]))
    if booking is None or booking.status != BOOKED:
        return
    gym_class = db.get(GymClass, booking.class_id)
    member = db.get(Member, booking.member_id)
    if gym_class is None or gym_class.cancelled_at is not None or member is None:
        return
    gym = db.get(Gym, gym_class.gym_id)
    assert gym is not None
    _tell(db, gym, member, class_text.REMINDER, gym_class, url=f"/{gym.slug}/classes")


def _log(
    db: Session,
    booking: ClassBooking,
    action: str,
    *,
    staff: StaffUser | None,
    member: Member | None,
) -> None:
    """By the desk, by the member in their app, or (the waitlist) by us."""
    changes = {
        "class_id": booking.class_id,
        "member_id": booking.member_id,
        "status": booking.status,
    }
    where = {"entity": "class_booking", "entity_id": booking.id, "changes": changes}
    if staff is not None:
        activity.staff_action(db, staff, action, **where)
    elif member is not None:
        activity.member_action(db, member, action, **where)
    else:
        activity.record(
            db,
            gym_id=booking.gym_id,
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            action=action,
            **where,
        )


def _changed(db: Session, gym_class: GymClass, member_id: uuid.UUID | None) -> None:
    live.publish(
        db,
        gym_id=gym_class.gym_id,
        kind=live.CLASS,
        member_id=member_id,
        branch_id=gym_class.branch_id,
    )


# --- the month, on Reports ---------------------------------------------------------


@dataclass
class TypeMonth:
    name: str
    held: int = 0
    places: int = 0
    booked: int = 0
    came: int = 0


@dataclass
class Month:
    held: int
    places: int
    booked: int
    came: int
    no_shows: int
    by_type: list[TypeMonth]
    # (instructor id, name, classes held, members who came)
    by_instructor: list[tuple[uuid.UUID, str, int, int]]


def month(
    db: Session, ctx: StaffContext, start: dt.datetime, end: dt.datetime
) -> Month | None:
    """Classes held (not cancelled, over) in [start, end) at the caller's
    branches: None for a gym that has never had a class. Three queries."""
    if (
        db.scalar(select(ClassType.id).where(ClassType.gym_id == ctx.gym_id).limit(1))
        is None
    ):
        return None
    held = [
        GymClass.gym_id == ctx.gym_id,
        GymClass.cancelled_at.is_(None),
        GymClass.starts_at >= start,
        GymClass.starts_at < end,
        GymClass.ends_at <= utcnow(),
    ]
    if ctx.branch_ids is not None:
        held.append(GymClass.branch_id.in_(ctx.branch_ids))
    classes = db.execute(
        select(GymClass.id, GymClass.places, GymClass.instructor_id, ClassType.name)
        .join(ClassType, ClassType.id == GymClass.type_id)
        .where(*held)
    ).all()
    came_expr = or_(
        ClassBooking.attended.is_(True),
        and_(ClassBooking.attended.is_(None), _came_at_door()),
    )
    bookings = db.execute(
        select(ClassBooking.class_id, came_expr)
        .join(GymClass, GymClass.id == ClassBooking.class_id)
        .where(ClassBooking.status == BOOKED, *held)
    ).all()
    booked: dict[uuid.UUID, int] = defaultdict(int)
    came: dict[uuid.UUID, int] = defaultdict(int)
    for class_id, did in bookings:
        booked[class_id] += 1
        came[class_id] += bool(did)
    types: dict[str, TypeMonth] = {}
    teaching: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0])
    for class_id, places, instructor_id, name in classes:
        row = types.setdefault(name, TypeMonth(name=name))
        row.held += 1
        row.places += places
        row.booked += booked[class_id]
        row.came += came[class_id]
        if instructor_id:
            teaching[instructor_id][0] += 1
            teaching[instructor_id][1] += came[class_id]
    names = (
        dict(
            db.execute(
                select(StaffUser.id, StaffUser.name).where(
                    StaffUser.id.in_(list(teaching))
                )
            ).all()
        )
        if teaching
        else {}
    )
    total_booked = sum(booked.values())
    total_came = sum(came.values())
    return Month(
        held=len(classes),
        places=sum(p for _, p, _, _ in classes),
        booked=total_booked,
        came=total_came,
        no_shows=total_booked - total_came,
        by_type=sorted(types.values(), key=lambda t: -t.held),
        by_instructor=sorted(
            ((i, names.get(i, ""), h, c) for i, (h, c) in teaching.items()),
            key=lambda row: -row[2],
        ),
    )
