import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import OptionalEmail, Phone, Strict
from app.schemas.money import PaymentIn, PaymentRead

Gender = Literal["male", "female", "other"]


class MemberFields(Strict):
    name: str = Field(min_length=1, max_length=120)
    phone: Phone
    email: OptionalEmail = None
    gender: Gender | None = None
    date_of_birth: dt.date | None = None
    address: str | None = Field(default=None, max_length=255)
    emergency_contact: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    home_branch_id: uuid.UUID | None = None
    joined_on: dt.date | None = None


class SaleFields(Strict):
    plan_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    price: int | None = Field(default=None, ge=0, le=10_000_000_00)
    discount: int = Field(default=0, ge=0, le=10_000_000_00)
    admission_fee: int | None = Field(default=None, ge=0, le=10_000_000_00)
    payment: PaymentIn | None = None


class MemberCreate(MemberFields):
    """Add a member, and optionally sell their first membership in one step."""

    membership: SaleFields | None = None


class MemberUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: Phone | None = None
    email: OptionalEmail = None
    gender: Gender | None = None
    date_of_birth: dt.date | None = None
    address: str | None = Field(default=None, max_length=255)
    emergency_contact: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    home_branch_id: uuid.UUID | None = None
    joined_on: dt.date | None = None

    @field_validator("name", "phone", "joined_on", "home_branch_id")
    @classmethod
    def required_fields_not_null(cls, value):
        if value is None:
            raise ValueError("This field can't be empty.")
        return value


class FreezeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_date: dt.date
    to_date: dt.date
    reason: str | None


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    plan_id: uuid.UUID | None
    plan_name: str
    branch_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    price: int
    discount: int
    admission_fee: int
    cancelled_at: dt.datetime | None
    cancel_reason: str | None
    source: str
    created_at: dt.datetime
    # Computed, never stored.
    status: str = ""
    days_left: int = 0
    total: int = 0
    paid: int = 0
    dues: int = 0
    freezes: list[FreezeRead] = []


class CurrentMembership(BaseModel):
    id: uuid.UUID
    plan_name: str
    start_date: dt.date
    end_date: dt.date


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_code: str
    name: str
    phone: str
    email: str | None
    gender: str | None
    date_of_birth: dt.date | None
    address: str | None
    emergency_contact: str | None
    notes: str | None
    home_branch_id: uuid.UUID
    joined_on: dt.date
    app_access: bool
    is_archived: bool
    created_at: dt.datetime
    photo_url: str | None = None
    # Where they stand today (app/services/members.py).
    status: str = ""
    current: CurrentMembership | None = None
    valid_until: dt.date | None = None
    days_left: int = 0
    dues: int = 0


class MemberList(BaseModel):
    items: list[MemberRead]
    total: int


class MemberDetail(MemberRead):
    memberships: list[MembershipRead]
    payments: list[PaymentRead]
    renewal_starts_on: dt.date
    first_membership: bool


class PhoneMatch(BaseModel):
    id: uuid.UUID
    name: str
    member_code: str


class MemberCreated(BaseModel):
    member: MemberDetail
    membership_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    same_phone: list[PhoneMatch] = []


class ArchiveIn(Strict):
    reason: str | None = Field(default=None, max_length=500)


class MembershipUpdate(Strict):
    plan_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    price: int | None = Field(default=None, ge=0, le=10_000_000_00)
    discount: int | None = Field(default=None, ge=0, le=10_000_000_00)
    admission_fee: int | None = Field(default=None, ge=0, le=10_000_000_00)
    reason: str | None = Field(default=None, max_length=500)


class ExtendIn(Strict):
    days: int = Field(ge=1, le=366)
    reason: str = Field(min_length=3, max_length=500)


class ExtendAllIn(ExtendIn):
    branch_id: uuid.UUID | None = None


class ExtendAllResult(BaseModel):
    extended: int


class FreezeIn(Strict):
    from_date: dt.date
    to_date: dt.date
    reason: str | None = Field(default=None, max_length=500)


class CancelIn(Strict):
    reason: str = Field(min_length=3, max_length=500)
    refund: PaymentIn | None = None


class HistoryEntry(BaseModel):
    id: uuid.UUID
    at: dt.datetime
    action: str
    actor_name: str | None
    changes: dict | None
    reason: str | None


class SaleResult(BaseModel):
    membership: MembershipRead
    payment: PaymentRead | None
