"""Group classes (PLAN.md §19.4)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import Strict

COLORS = Literal["blue", "teal", "green", "amber", "orange", "red", "pink", "purple"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ClassTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    minutes: int
    places: int
    color: str
    is_active: bool
    sort_order: int


class ClassTypeCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    minutes: int = Field(default=60, ge=10, le=300)
    places: int = Field(default=20, ge=1, le=500)
    color: COLORS = "blue"
    sort_order: int = 0


class ClassTypeUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    minutes: int | None = Field(default=None, ge=10, le=300)
    places: int | None = Field(default=None, ge=1, le=500)
    color: COLORS | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ClassSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID
    type_id: uuid.UUID
    weekday: int
    starts: str
    minutes: int
    places: int
    instructor_id: uuid.UUID | None
    is_active: bool


class ClassSlotCreate(Strict):
    branch_id: uuid.UUID
    type_id: uuid.UUID
    # 0 is Monday.
    weekday: int = Field(ge=0, le=6)
    starts: str = Field(pattern=HHMM)
    # The type's, unless given.
    minutes: int | None = Field(default=None, ge=10, le=300)
    places: int | None = Field(default=None, ge=1, le=500)
    instructor_id: uuid.UUID | None = None


class ClassSlotUpdate(Strict):
    type_id: uuid.UUID | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    starts: str | None = Field(default=None, pattern=HHMM)
    minutes: int | None = Field(default=None, ge=10, le=300)
    places: int | None = Field(default=None, ge=1, le=500)
    # Null takes the instructor off: sent explicitly, so not dropped.
    instructor_id: uuid.UUID | None = None
    is_active: bool | None = None


class Instructor(BaseModel):
    id: uuid.UUID
    name: str


class ClassRead(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    type_id: uuid.UUID
    type_name: str
    color: str
    slot_id: uuid.UUID | None
    starts_at: dt.datetime
    ends_at: dt.datetime
    instructor_id: uuid.UUID | None
    instructor_name: str | None
    places: int
    booked: int
    waiting: int
    cancelled_at: dt.datetime | None
    cancel_reason: str | None


class BookingRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    member_id: uuid.UUID
    member_name: str
    member_code: str
    photo_url: str | None
    status: str
    booked_at: dt.datetime
    cancelled_at: dt.datetime | None
    late: bool
    source: str
    # The instructor's tick; and whether they came, by it or by the door.
    attended: bool | None
    came: bool


class ClassDetail(ClassRead):
    bookings: list[BookingRead]


class ClassCreate(Strict):
    """A class once, outside the timetable."""

    branch_id: uuid.UUID
    type_id: uuid.UUID
    starts_at: dt.datetime
    minutes: int | None = Field(default=None, ge=10, le=300)
    places: int | None = Field(default=None, ge=1, le=500)
    instructor_id: uuid.UUID | None = None


class ClassUpdate(Strict):
    """Move one class, or change its instructor or places."""

    starts_at: dt.datetime | None = None
    minutes: int | None = Field(default=None, ge=10, le=300)
    places: int | None = Field(default=None, ge=1, le=500)
    instructor_id: uuid.UUID | None = None


class ClassCancelIn(Strict):
    reason: str = Field(min_length=3, max_length=300)
    # Also by SMS to those push can't reach (costs credits).
    sms: bool = False


class BookIn(Strict):
    member_id: uuid.UUID


class AttendedIn(Strict):
    came: bool


class MemberBookingRead(BaseModel):
    """A member's booking on their profile's Classes tab."""

    id: uuid.UUID
    class_id: uuid.UUID
    type_name: str
    starts_at: dt.datetime
    status: str
    late: bool
    cancelled: bool
    came: bool | None


class MemberClasses(BaseModel):
    bookings: list[MemberBookingRead]
    no_shows: int


# --- the member app ---


class AppClass(BaseModel):
    id: uuid.UUID
    type_name: str
    color: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    instructor_name: str | None
    places: int
    places_left: int
    waiting: int
    cancelled: bool
    # Theirs: booked, waitlist, or none; and the booking to cancel.
    mine: Literal["booked", "waitlist"] | None
    booking_id: uuid.UUID | None
    # Why they can't book it, if they can't (no_membership, plan_no_class,
    # branch, frozen, no_shows); booking not open or closed is the app's to
    # tell from the times.
    blocked: str | None


class AppClasses(BaseModel):
    classes: list[AppClass]
    booking_days: int
    closes_minutes: int
    cancel_hours: int
    no_shows: int
