"""Personal training (PLAN.md §18.3)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import Strict
from app.schemas.money import PaymentIn, PaymentRead
from app.schemas.plans import MAX_PAISA

Kind = Literal["monthly", "sessions"]


class PtPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Kind
    sessions: int | None
    duration_months: int | None
    duration_days: int | None
    price: int
    is_active: bool
    sort_order: int


class PtPlanCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    kind: Kind
    # How many sessions a pack holds; none for monthly training.
    sessions: int | None = Field(default=None, ge=1, le=500)
    duration_months: int | None = Field(default=None, ge=1, le=24)
    duration_days: int | None = Field(default=None, ge=1, le=730)
    price: int = Field(ge=0, le=MAX_PAISA)
    sort_order: int = 0

    @model_validator(mode="after")
    def consistent(self) -> "PtPlanCreate":
        if (self.duration_months is None) == (self.duration_days is None):
            raise ValueError("Give a duration in months or in days.")
        if (self.kind == "sessions") != (self.sessions is not None):
            raise ValueError("A pack of sessions says how many; monthly doesn't.")
        return self


class PtPlanUpdate(Strict):
    """Changes apply to what is sold from now on; sold packages keep their terms."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Kind | None = None
    sessions: int | None = Field(default=None, ge=1, le=500)
    duration_months: int | None = Field(default=None, ge=1, le=24)
    duration_days: int | None = Field(default=None, ge=1, le=730)
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    is_active: bool | None = None
    sort_order: int | None = None


class Trainer(BaseModel):
    id: uuid.UUID
    name: str


class PtSaleIn(Strict):
    plan_id: uuid.UUID
    trainer_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    # Today unless given; the end from the plan's length in the gym's calendar.
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    # The plan's price unless given.
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    discount: int = Field(default=0, ge=0, le=MAX_PAISA)
    payment: PaymentIn | None = None


class PtPackageUpdate(Strict):
    """Another trainer, or other dates."""

    trainer_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    reason: str | None = Field(default=None, max_length=500)


class PtCancelIn(Strict):
    reason: str = Field(min_length=3, max_length=500)
    refund: PaymentIn | None = None


class SessionIn(Strict):
    # Today unless given: a session trained earlier, recorded late.
    trained_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=500)


class PtSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    package_id: uuid.UUID
    trained_on: dt.date
    trainer_id: uuid.UUID
    trainer_name: str | None = None
    recorded_by_name: str | None = None
    note: str | None
    created_at: dt.datetime
    voided_at: dt.datetime | None
    void_reason: str | None


class PtPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    member_name: str = ""
    member_code: str = ""
    plan_id: uuid.UUID | None
    plan_name: str
    kind: Kind
    # The pack's size; none for monthly training.
    sessions: int | None
    trainer_id: uuid.UUID
    trainer_name: str | None = None
    branch_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    price: int
    discount: int
    cancelled_at: dt.datetime | None
    cancel_reason: str | None
    created_at: dt.datetime
    # Computed (app/services/training.py), never stored.
    status: str = ""
    sessions_used: int = 0
    sessions_left: int | None = None
    days_left: int = 0
    last_session_on: dt.date | None = None
    total: int = 0
    paid: int = 0
    dues: int = 0


class PtPackageDetail(PtPackageRead):
    """On the member's profile: every session, voided too, and the money."""

    session_log: list[PtSessionRead] = []
    payments: list[PaymentRead] = []


class PtSaleResult(BaseModel):
    package: PtPackageDetail
    payment: PaymentRead | None


class MemberTraining(BaseModel):
    """Their personal training on the app's Home (§18.3)."""

    id: uuid.UUID
    plan_name: str
    kind: Kind
    status: str
    trainer_name: str | None
    start_date: dt.date
    end_date: dt.date
    sessions: int | None
    sessions_left: int | None
    days_left: int
    # Still to pay for it: its own, never in the membership's dues.
    dues: int
