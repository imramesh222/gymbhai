"""Group classes: Zumba, yoga, aerobics at fixed times, booked from the app
with places counted (PLAN.md §19.4).

A weekly timetable (class slots) makes each class 4 weeks ahead, so one class
can be moved, given another instructor or cancelled on its own. A booking is
a member's place in a class, or on its waitlist.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

BOOKED = "booked"
WAITLIST = "waitlist"
CANCELLED = "cancelled"
BOOKING_STATUSES = (BOOKED, WAITLIST, CANCELLED)

SOURCE_APP = "app"
SOURCE_DESK = "desk"


class ClassType(IdMixin, TimestampMixin, GymOwned, Base):
    """Zumba, yoga: what a class is, and its usual length and places."""

    __tablename__ = "class_types"
    __table_args__ = (
        CheckConstraint("minutes BETWEEN 10 AND 300", name="minutes"),
        CheckConstraint("places BETWEEN 1 AND 500", name="places"),
    )

    name: Mapped[str] = mapped_column(String(80))
    minutes: Mapped[int] = mapped_column(Integer, default=60)
    places: Mapped[int] = mapped_column(Integer, default=20)
    # One of the chart palette's names, so the timetable reads at a glance.
    color: Mapped[str] = mapped_column(String(16), default="blue")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )


class ClassSlot(IdMixin, TimestampMixin, GymOwned, Base):
    """The weekly timetable: Zumba, Mondays 07:00 at Baneshwor."""

    __tablename__ = "class_slots"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("minutes BETWEEN 10 AND 300", name="minutes"),
        CheckConstraint("places BETWEEN 1 AND 500", name="places"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_types.id")
    )
    # 0 is Monday, as for access hours.
    weekday: Mapped[int] = mapped_column(Integer)
    # "HH:MM" in Nepal time.
    starts: Mapped[str] = mapped_column(String(5))
    minutes: Mapped[int] = mapped_column(Integer)
    places: Mapped[int] = mapped_column(Integer)
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )


class GymClass(IdMixin, TimestampMixin, GymOwned, Base):
    """One class on one day, made from a slot (or added once)."""

    __tablename__ = "classes"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="times"),
        CheckConstraint("places BETWEEN 1 AND 500", name="places"),
        # Made from the timetable once, however often the worker runs.
        UniqueConstraint("slot_id", "starts_at", name="uq_classes_slot_start"),
        Index("ix_classes_gym_starts", "gym_id", "starts_at"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_types.id")
    )
    slot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_slots.id", ondelete="SET NULL")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    places: Mapped[int] = mapped_column(Integer)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class ClassBooking(IdMixin, TimestampMixin, GymOwned, Base):
    """A member's place in a class, or on its waitlist."""

    __tablename__ = "class_bookings"
    __table_args__ = (
        CheckConstraint("status IN ('booked', 'waitlist', 'cancelled')", name="status"),
        # One place each, or one spot in the queue: a cancelled one doesn't
        # count, so a member can book again.
        Index(
            "uq_class_bookings_member",
            "class_id",
            "member_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    # The waitlist's order.
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cancelled after the gym's cut-off.
    late: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Ticked by the instructor; null until they do. Who came without a tick
    # is worked out from the door's check-ins.
    attended: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(8), default=SOURCE_APP)
    booked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


# Classes a membership lets one book (§19.4), on plans and copied onto each
# membership sold, like visits and hours.
CLASSES_NONE = "none"
CLASSES_ALL = "all"
CLASSES_CHOSEN = "chosen"
