import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import MIN_PASSWORD_LENGTH, Strict

MAX_PAISA = 10_000_000_00


class PlatformPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    max_active_members: int | None
    max_branches: int | None
    monthly_price: int | None
    included_sms: int
    is_active: bool


class PlatformPlanIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    max_active_members: int | None = Field(default=None, ge=1)
    max_branches: int | None = Field(default=None, ge=1)
    monthly_price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    included_sms: int = Field(default=0, ge=0)
    is_active: bool = True


class PlatformPlanUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    max_active_members: int | None = Field(default=None, ge=1)
    max_branches: int | None = Field(default=None, ge=1)
    monthly_price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    included_sms: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SubscriptionPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gym_id: uuid.UUID
    kind: str
    platform_plan_id: uuid.UUID | None
    months: int | None
    sms_credits: int | None
    amount: int
    transaction_ref: str | None
    status: str
    reject_reason: str | None
    reviewed_at: dt.datetime | None
    created_at: dt.datetime
    gym_name: str | None = None
    plan_name: str | None = None


class SubscriptionPaymentIn(Strict):
    kind: Literal["subscription", "sms"] = "subscription"
    platform_plan_id: uuid.UUID | None = None
    months: int | None = Field(default=None, ge=1, le=24)
    sms_credits: int | None = Field(default=None, ge=1, le=1_000_000)
    amount: int = Field(gt=0, le=MAX_PAISA)
    transaction_ref: str = Field(min_length=3, max_length=64)

    @model_validator(mode="after")
    def complete(self) -> "SubscriptionPaymentIn":
        if self.kind == "subscription" and not (self.platform_plan_id and self.months):
            raise ValueError("Choose a plan and how many months.")
        if self.kind == "sms" and not self.sms_credits:
            raise ValueError("Say how many SMS credits.")
        return self


class SubscriptionOverview(BaseModel):
    status: str
    plan_name: str | None
    starts_on: dt.date | None
    ends_on: dt.date | None
    days_left: int
    phase: str
    grace_ends_on: dt.date | None
    active_members: int
    max_active_members: int | None
    over_limit: bool
    sms_balance: int
    plans: list[PlatformPlanRead]
    payments: list[SubscriptionPaymentRead]
    # Where to pay us: shown on the subscription screen.
    pay_to: dict[str, str | None]


# --- /admin ---------------------------------------------------------------------


class AdminGym(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    owner_name: str | None
    owner_phone: str | None
    owner_email: str | None
    created_at: dt.datetime
    subscription_status: str
    plan_name: str | None
    ends_on: dt.date | None
    phase: str
    active_members: int
    sms_balance: int
    pending_payments: int


class GrantIn(Strict):
    platform_plan_id: uuid.UUID | None = None
    months: int | None = Field(default=None, ge=1, le=36)
    ends_on: dt.date | None = None

    @model_validator(mode="after")
    def one(self) -> "GrantIn":
        if not self.months and not self.ends_on:
            raise ValueError("Give months or an end date.")
        return self


class CreditsIn(Strict):
    credits: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=2, max_length=120)


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class ApproveSubscriptionIn(Strict):
    """Defaults to what the gym asked for; the admin may change it."""

    platform_plan_id: uuid.UUID | None = None
    months: int | None = Field(default=None, ge=1, le=36)
    sms_credits: int | None = Field(default=None, ge=1, le=1_000_000)


class OwnerPasswordIn(Strict):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=72)
