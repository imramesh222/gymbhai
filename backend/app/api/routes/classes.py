"""Group classes (PLAN.md §19.4): class types and the weekly timetable, each
class with its roster, booking at the desk and from the member app."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import current_member, require, require_any
from app.api.routes.members import load_member
from app.api.tenancy import StaffContext, for_gym, get_in_gym, in_branches
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import get_db
from app.models.classes import (
    BOOKED,
    CANCELLED,
    ClassBooking,
    ClassSlot,
    ClassType,
    GymClass,
)
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.staff import StaffUser
from app.schemas.classes import (
    AppClass,
    AppClasses,
    AttendedIn,
    BookIn,
    BookingRead,
    ClassCancelIn,
    ClassCreate,
    ClassDetail,
    ClassRead,
    ClassSlotCreate,
    ClassSlotRead,
    ClassSlotUpdate,
    ClassTypeCreate,
    ClassTypeRead,
    ClassTypeUpdate,
    ClassUpdate,
    Instructor,
    MemberBookingRead,
    MemberClasses,
)
from app.services import activity, storage
from app.services import classes as service

router = APIRouter(tags=["classes"])
member_router = APIRouter(prefix="/m", tags=["member app"])

ANY = require_any(
    Permission.CLASSES_TEACH, Permission.CLASSES_BOOK, Permission.CLASSES_MANAGE
)
MANAGE = require(Permission.CLASSES_MANAGE)
BOOK = require(Permission.CLASSES_BOOK)
# The plan form lists the classes a plan includes.
SEE_TYPES = require_any(
    Permission.CLASSES_TEACH,
    Permission.CLASSES_BOOK,
    Permission.CLASSES_MANAGE,
    Permission.SETUP_PLANS,
)
WEEK = dt.timedelta(days=7)


# --- reading ----------------------------------------------------------------------


def classes_read(db: Session, rows: Sequence[GymClass]) -> list[ClassRead]:
    """With names and counts: one query each, however many classes."""
    if not rows:
        return []
    types = {
        t.id: t
        for t in db.scalars(
            select(ClassType).where(ClassType.id.in_({r.type_id for r in rows}))
        )
    }
    teacher_ids = {r.instructor_id for r in rows if r.instructor_id}
    teachers = (
        dict(
            db.execute(
                select(StaffUser.id, StaffUser.name).where(
                    StaffUser.id.in_(teacher_ids)
                )
            ).all()
        )
        if teacher_ids
        else {}
    )
    taken = service.counts(db, [r.id for r in rows])
    return [
        ClassRead(
            id=r.id,
            branch_id=r.branch_id,
            type_id=r.type_id,
            type_name=types[r.type_id].name,
            color=types[r.type_id].color,
            slot_id=r.slot_id,
            starts_at=r.starts_at,
            ends_at=r.ends_at,
            instructor_id=r.instructor_id,
            instructor_name=teachers.get(r.instructor_id) if r.instructor_id else None,
            places=r.places,
            booked=taken[r.id].booked,
            waiting=taken[r.id].waiting,
            cancelled_at=r.cancelled_at,
            cancel_reason=r.cancel_reason,
        )
        for r in rows
    ]


def detail(db: Session, gym_class: GymClass) -> ClassDetail:
    rows = db.execute(
        select(ClassBooking, Member)
        .join(Member, Member.id == ClassBooking.member_id)
        .where(ClassBooking.class_id == gym_class.id)
        .order_by(ClassBooking.status != BOOKED, ClassBooking.booked_at)
    ).all()
    came = service.came_at_door(db, [(b, gym_class) for b, _ in rows])
    bookings = [
        BookingRead(
            id=b.id,
            class_id=b.class_id,
            member_id=m.id,
            member_name=m.name,
            member_code=m.member_code,
            photo_url=storage.signed_url(m.photo_key),
            status=b.status,
            booked_at=b.booked_at,
            cancelled_at=b.cancelled_at,
            late=b.late,
            source=b.source,
            attended=b.attended,
            came=b.attended if b.attended is not None else b.id in came,
        )
        for b, m in rows
    ]
    [read] = classes_read(db, [gym_class])
    return ClassDetail(**read.model_dump(), bookings=bookings)


def load_class(
    db: Session, ctx: StaffContext, class_id: uuid.UUID, *, for_update: bool = False
) -> GymClass:
    return get_in_gym(
        db,
        GymClass,
        class_id,
        ctx,
        branch_column=GymClass.branch_id,
        message="No such class.",
        for_update=for_update,
    )


def load_booking(
    db: Session, ctx: StaffContext, booking_id: uuid.UUID
) -> tuple[ClassBooking, GymClass]:
    booking = get_in_gym(db, ClassBooking, booking_id, ctx, message="No such booking.")
    return booking, load_class(db, ctx, booking.class_id)


def _gym(db: Session, gym_id: uuid.UUID) -> Gym:
    gym = db.get(Gym, gym_id)
    assert gym is not None
    return gym


# --- class types --------------------------------------------------------------------


@router.get("/class-types", response_model=list[ClassTypeRead])
def list_types(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SEE_TYPES)
) -> list[ClassType]:
    stmt = for_gym(select(ClassType), ClassType, ctx)
    return list(db.scalars(stmt.order_by(ClassType.sort_order, ClassType.name)))


@router.post(
    "/class-types", response_model=ClassTypeRead, status_code=status.HTTP_201_CREATED
)
def create_type(
    payload: ClassTypeCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassType:
    row = ClassType(gym_id=ctx.gym_id, **payload.model_dump())
    db.add(row)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "class_type.created",
        entity="class_type",
        entity_id=row.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return row


@router.patch("/class-types/{type_id}", response_model=ClassTypeRead)
def update_type(
    type_id: uuid.UUID,
    payload: ClassTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassType:
    row = get_in_gym(db, ClassType, type_id, ctx, message="No such class.")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    before = {k: getattr(row, k) for k in changes}
    for key, value in changes.items():
        setattr(row, key, value)
    diff = activity.diff(before, changes)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "class_type.updated",
            entity="class_type",
            entity_id=row.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return row


# --- the timetable ------------------------------------------------------------------


def _branch(db: Session, ctx: StaffContext, branch_id: uuid.UUID) -> Branch:
    return get_in_gym(
        db, Branch, branch_id, ctx, branch_column=Branch.id, message="No such branch."
    )


@router.get("/class-slots", response_model=list[ClassSlotRead])
def list_slots(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ANY),
    branch_id: uuid.UUID | None = None,
) -> list[ClassSlot]:
    stmt = in_branches(
        for_gym(select(ClassSlot), ClassSlot, ctx), ClassSlot.branch_id, ctx
    ).where(ClassSlot.is_active)
    if branch_id is not None:
        stmt = stmt.where(ClassSlot.branch_id == branch_id)
    return list(db.scalars(stmt.order_by(ClassSlot.weekday, ClassSlot.starts)))


@router.post(
    "/class-slots", response_model=ClassSlotRead, status_code=status.HTTP_201_CREATED
)
def create_slot(
    payload: ClassSlotCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassSlot:
    branch = _branch(db, ctx, payload.branch_id)
    kind = get_in_gym(db, ClassType, payload.type_id, ctx, message="No such class.")
    service.check_instructor(db, ctx.gym_id, payload.instructor_id)
    slot = ClassSlot(
        gym_id=ctx.gym_id,
        branch_id=branch.id,
        type_id=kind.id,
        weekday=payload.weekday,
        starts=payload.starts,
        minutes=payload.minutes or kind.minutes,
        places=payload.places or kind.places,
        instructor_id=payload.instructor_id,
    )
    db.add(slot)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "class_slot.created",
        entity="class_slot",
        entity_id=slot.id,
        changes=ClassSlotRead.model_validate(slot).model_dump(),
        request=request,
    )
    service.sync_slot(db, slot)
    db.commit()
    return slot


@router.patch("/class-slots/{slot_id}", response_model=ClassSlotRead)
def update_slot(
    slot_id: uuid.UUID,
    payload: ClassSlotUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassSlot:
    """Changes the classes nobody has booked yet; booked ones stay as they
    are, for the desk to move or cancel."""
    slot = get_in_gym(
        db,
        ClassSlot,
        slot_id,
        ctx,
        branch_column=ClassSlot.branch_id,
        message="No such class.",
        for_update=True,
    )
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("type_id") is not None:
        get_in_gym(db, ClassType, changes["type_id"], ctx, message="No such class.")
    if "instructor_id" in changes:
        service.check_instructor(db, ctx.gym_id, changes["instructor_id"])
    before = ClassSlotRead.model_validate(slot).model_dump()
    for key, value in changes.items():
        if value is None and key != "instructor_id":
            continue
        setattr(slot, key, value)
    db.flush()
    diff = activity.diff(before, ClassSlotRead.model_validate(slot).model_dump())
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "class_slot.updated",
            entity="class_slot",
            entity_id=slot.id,
            changes=diff,
            request=request,
        )
    service.sync_slot(db, slot)
    db.commit()
    return slot


@router.get("/class-instructors", response_model=list[Instructor])
def list_instructors(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(ANY)
) -> list[Instructor]:
    return [
        Instructor(id=s.id, name=s.name) for s in service.instructors(db, ctx.gym_id)
    ]


# --- classes -----------------------------------------------------------------------


@router.get("/classes", response_model=list[ClassRead])
def list_classes(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ANY),
    start: Annotated[dt.date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    branch_id: uuid.UUID | None = None,
    mine: bool = False,
) -> list[ClassRead]:
    """A week (or a few days) from `from`, today unless given. `mine`: the
    caller's own classes, for an instructor."""
    first = start or today_in_nepal()
    begins = dt.datetime.combine(first, dt.time(), tzinfo=NEPAL)
    stmt = in_branches(
        for_gym(select(GymClass), GymClass, ctx), GymClass.branch_id, ctx
    ).where(
        GymClass.starts_at >= begins,
        GymClass.starts_at < begins + dt.timedelta(days=days),
    )
    if branch_id is not None:
        stmt = stmt.where(GymClass.branch_id == branch_id)
    if mine:
        stmt = stmt.where(GymClass.instructor_id == ctx.staff.id)
    return classes_read(db, list(db.scalars(stmt.order_by(GymClass.starts_at))))


@router.get("/classes/mine", response_model=list[ClassRead])
def my_teaching(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.CLASSES_TEACH)),
    start: Annotated[dt.date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
) -> list[ClassRead]:
    """An instructor's own classes: My classes."""
    first = start or today_in_nepal()
    begins = dt.datetime.combine(first, dt.time(), tzinfo=NEPAL)
    stmt = for_gym(select(GymClass), GymClass, ctx).where(
        GymClass.instructor_id == ctx.staff.id,
        GymClass.starts_at >= begins,
        GymClass.starts_at < begins + dt.timedelta(days=days),
    )
    return classes_read(db, list(db.scalars(stmt.order_by(GymClass.starts_at))))


@router.post(
    "/classes", response_model=ClassDetail, status_code=status.HTTP_201_CREATED
)
def create_class(
    payload: ClassCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassDetail:
    branch = _branch(db, ctx, payload.branch_id)
    kind = get_in_gym(db, ClassType, payload.type_id, ctx, message="No such class.")
    service.check_instructor(db, ctx.gym_id, payload.instructor_id)
    if payload.starts_at <= utcnow():
        raise AppError(422, "in_the_past", "That time has passed.")
    gym_class = GymClass(
        gym_id=ctx.gym_id,
        branch_id=branch.id,
        type_id=kind.id,
        starts_at=payload.starts_at,
        ends_at=payload.starts_at
        + dt.timedelta(minutes=payload.minutes or kind.minutes),
        places=payload.places or kind.places,
        instructor_id=payload.instructor_id,
    )
    db.add(gym_class)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "class.created",
        entity="class",
        entity_id=gym_class.id,
        request=request,
    )
    service._changed(db, gym_class, None)
    db.commit()
    return detail(db, gym_class)


@router.get("/classes/{class_id}", response_model=ClassDetail)
def get_class(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ANY),
) -> ClassDetail:
    return detail(db, load_class(db, ctx, class_id))


@router.patch("/classes/{class_id}", response_model=ClassDetail)
def update_class(
    class_id: uuid.UUID,
    payload: ClassUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassDetail:
    """Move one class, or change its instructor or places. Fewer places than
    are booked is refused: cancel bookings first."""
    gym_class = load_class(db, ctx, class_id, for_update=True)
    if gym_class.cancelled_at is not None:
        raise AppError(409, "class_cancelled", "This class is cancelled.")
    changes = payload.model_dump(exclude_unset=True)
    before = {
        "starts_at": gym_class.starts_at,
        "ends_at": gym_class.ends_at,
        "places": gym_class.places,
        "instructor_id": gym_class.instructor_id,
    }
    if "instructor_id" in changes:
        service.check_instructor(db, ctx.gym_id, changes["instructor_id"])
        gym_class.instructor_id = changes["instructor_id"]
    length = gym_class.ends_at - gym_class.starts_at
    if changes.get("minutes"):
        length = dt.timedelta(minutes=changes["minutes"])
    was = gym_class.starts_at
    if changes.get("starts_at"):
        if changes["starts_at"] <= utcnow():
            raise AppError(422, "in_the_past", "That time has passed.")
        gym_class.starts_at = changes["starts_at"]
    gym_class.ends_at = gym_class.starts_at + length
    if changes.get("places"):
        taken = service.counts(db, [gym_class.id])[gym_class.id].booked
        if changes["places"] < taken:
            raise AppError(
                409,
                "places_taken",
                f"{taken} places are booked already.",
                booked=taken,
            )
        gym_class.places = changes["places"]
        service.promote(db, _gym(db, ctx.gym_id), gym_class)
    after = {key: getattr(gym_class, key) for key in before}
    activity.staff_action(
        db,
        ctx.staff,
        "class.updated",
        entity="class",
        entity_id=gym_class.id,
        changes=activity.diff(before, after),
        request=request,
    )
    if gym_class.starts_at != was:
        # Everyone booked or waiting hears the new time (§19.4).
        service.moved(
            db, _gym(db, ctx.gym_id), gym_class, was, sms=changes.get("sms", False)
        )
    service._changed(db, gym_class, None)
    db.commit()
    return detail(db, gym_class)


@router.post("/classes/{class_id}/cancel", response_model=ClassDetail)
def cancel_class(
    class_id: uuid.UUID,
    payload: ClassCancelIn,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> ClassDetail:
    gym_class = load_class(db, ctx, class_id)
    service.cancel_class(db, ctx, gym_class, payload.reason, sms=payload.sms)
    db.commit()
    return detail(db, gym_class)


@router.post(
    "/classes/{class_id}/bookings",
    response_model=ClassDetail,
    status_code=status.HTTP_201_CREATED,
)
def book_member(
    class_id: uuid.UUID,
    payload: BookIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(BOOK),
) -> ClassDetail:
    """At the desk: a place, or the waitlist, until the class starts."""
    idem = idempotency.begin(db, ctx, request, payload)
    gym_class = load_class(db, ctx, class_id)
    member = load_member(db, ctx, payload.member_id)
    service.book(db, _gym(db, ctx.gym_id), member, gym_class, staff=ctx.staff)
    answer = detail(db, gym_class)
    idem.finish(answer)
    db.commit()
    return answer


@router.post("/class-bookings/{booking_id}/cancel", response_model=ClassDetail)
def cancel_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(BOOK),
) -> ClassDetail:
    booking, gym_class = load_booking(db, ctx, booking_id)
    service.cancel_booking(
        db, _gym(db, ctx.gym_id), booking, gym_class, staff=ctx.staff
    )
    db.commit()
    return detail(db, gym_class)


@router.post("/class-bookings/{booking_id}/attended", response_model=ClassDetail)
def mark_attended(
    booking_id: uuid.UUID,
    payload: AttendedIn,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ANY),
) -> ClassDetail:
    booking, gym_class = load_booking(db, ctx, booking_id)
    service.set_attended(db, ctx, booking, gym_class, payload.came)
    db.commit()
    return detail(db, gym_class)


@router.get("/members/{member_id}/classes", response_model=MemberClasses)
def member_classes(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> MemberClasses:
    """Their bookings, newest first, and their no-shows in the last 30 days."""
    member = load_member(db, ctx, member_id)
    rows = db.execute(
        select(ClassBooking, GymClass, ClassType.name)
        .join(GymClass, GymClass.id == ClassBooking.class_id)
        .join(ClassType, ClassType.id == GymClass.type_id)
        .where(ClassBooking.member_id == member.id)
        .order_by(GymClass.starts_at.desc())
        .limit(100)
    ).all()
    came = service.came_at_door(db, [(b, c) for b, c, _ in rows])
    now = utcnow()
    return MemberClasses(
        bookings=[
            MemberBookingRead(
                id=b.id,
                class_id=c.id,
                type_name=name,
                starts_at=c.starts_at,
                status=b.status,
                late=b.late,
                cancelled=c.cancelled_at is not None,
                came=(b.attended if b.attended is not None else b.id in came)
                if b.status == BOOKED and c.ends_at < now
                else None,
            )
            for b, c, name in rows
        ],
        no_shows=service.no_shows(db, member.id),
    )


# --- the member app -------------------------------------------------------------


def _app_classes(db: Session, member: Member, first: dt.date) -> AppClasses:
    gym = _gym(db, member.gym_id)
    config = gym.config
    begins = dt.datetime.combine(first, dt.time(), tzinfo=NEPAL)
    rows = list(
        db.scalars(
            select(GymClass)
            .where(
                GymClass.gym_id == member.gym_id,
                # Their branch's, and any they were booked into elsewhere.
                or_(
                    GymClass.branch_id == member.home_branch_id,
                    exists().where(
                        ClassBooking.class_id == GymClass.id,
                        ClassBooking.member_id == member.id,
                        ClassBooking.status != CANCELLED,
                    ),
                ),
                GymClass.starts_at >= max(begins, utcnow() - dt.timedelta(hours=2)),
                GymClass.starts_at < begins + WEEK,
            )
            .order_by(GymClass.starts_at)
        )
    )
    reads = classes_read(db, rows)
    mine = (
        {
            b.class_id: b
            for b in db.scalars(
                select(ClassBooking).where(
                    ClassBooking.member_id == member.id,
                    ClassBooking.class_id.in_([r.id for r in rows]),
                    ClassBooking.status != CANCELLED,
                )
            )
        }
        if rows
        else {}
    )
    # The member read once for the whole week, not once a class.
    known = service.eligibility(db, member)
    classes = []
    for row, read in zip(rows, reads, strict=True):
        booking = mine.get(row.id)
        blocked = service.why_not(db, gym, member, row, known)
        classes.append(
            AppClass(
                id=row.id,
                type_name=read.type_name,
                color=read.color,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                instructor_name=read.instructor_name,
                places=row.places,
                places_left=max(row.places - read.booked, 0),
                waiting=read.waiting,
                cancelled=row.cancelled_at is not None,
                mine=booking.status if booking else None,  # type: ignore[arg-type]
                booking_id=booking.id if booking else None,
                blocked=blocked[0] if blocked else None,
            )
        )
    return AppClasses(
        classes=classes,
        booking_days=config.class_booking_days,
        closes_minutes=config.class_closes_minutes,
        cancel_hours=config.class_cancel_hours,
        no_shows=known.no_shows,
    )


@member_router.get("/classes", response_model=AppClasses)
def my_classes(
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
    start: Annotated[dt.date | None, Query(alias="from")] = None,
) -> AppClasses:
    """The week's classes at their branch, with places left and theirs."""
    return _app_classes(db, member, start or today_in_nepal())


def _own_class(db: Session, member: Member, class_id: uuid.UUID) -> GymClass:
    gym_class = db.get(GymClass, class_id)
    if gym_class is None or gym_class.gym_id != member.gym_id:
        raise not_found("No such class.")
    return gym_class


@member_router.post("/classes/{class_id}/book", response_model=AppClasses)
def book_myself(
    class_id: uuid.UUID,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> AppClasses:
    """A place, or the waitlist. Once, however often it's tapped (§17.4)."""
    idem = idempotency.begin_member(db, member, request)
    gym_class = _own_class(db, member, class_id)
    service.book(db, _gym(db, member.gym_id), member, gym_class)
    answer = _app_classes(db, member, service.local_day(gym_class.starts_at))
    idem.finish(answer)
    db.commit()
    return answer


@member_router.post("/class-bookings/{booking_id}/cancel", response_model=AppClasses)
def cancel_my_booking(
    booking_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> AppClasses:
    booking = db.get(ClassBooking, booking_id)
    if booking is None or booking.member_id != member.id:
        raise not_found("No such booking.")
    gym_class = _own_class(db, member, booking.class_id)
    service.cancel_booking(db, _gym(db, member.gym_id), booking, gym_class)
    answer = _app_classes(db, member, service.local_day(gym_class.starts_at))
    db.commit()
    return answer
