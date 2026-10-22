import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import NewPassword, OptionalEmail, OptionalPhone, Strict

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


class PlatformSettingsRead(BaseModel):
    """Our own settings (§19.3): what a WhatsApp message costs a gym, in
    message credits (an SMS part is one), and whether WhatsApp can send."""

    whatsapp_credits: int
    whatsapp_available: bool
    # A gym's own app (§20.3), in paisa: offered once both are set.
    branded_app_setup_price: int | None = None
    branded_app_monthly_price: int | None = None


class PlatformSettingsUpdate(Strict):
    whatsapp_credits: int | None = Field(default=None, ge=1, le=20)
    branded_app_setup_price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    branded_app_monthly_price: int | None = Field(default=None, ge=0, le=MAX_PAISA)


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
    # app: the one-time fee for the gym's own app (§20.3).
    kind: Literal["subscription", "sms", "app"] = "subscription"
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
    # The gym's own app (§20.3): its monthly add-on, while built and live, and
    # its one-time fee until paid.
    app_monthly: int | None = None
    app_setup_due: int | None = None


# --- /admin ---------------------------------------------------------------------


class AdminGym(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    owner_name: str | None
    owner_phone: str | None
    owner_email: str | None
    owner_two_step: bool
    created_at: dt.datetime
    subscription_status: str
    plan_name: str | None
    ends_on: dt.date | None
    phase: str
    active_members: int
    sms_balance: int
    pending_payments: int
    # How it's doing (§16.5, 10.1, 10.2).
    state: str = "trial"  # trial, paying, grace, read_only, suspended
    last_sign_in_at: dt.datetime | None = None
    check_ins_7d: int = 0
    members_added_30d: int = 0
    going_quiet: bool = False
    setup: dict[str, bool] = {}


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
    new_password: NewPassword


class MonthCount(BaseModel):
    month: str
    gyms: int


class MonthSms(BaseModel):
    month: str
    credits: int
    amount: int


class AdminSummary(BaseModel):
    """The /admin home (§16.5, 10.1)."""

    mrr: int
    gyms: int
    by_state: dict[str, int]
    trial_conversion: float | None
    trials_ended: int
    trials_converted: int
    lost_by_month: list[MonthCount]
    sms_sold_by_month: list[MonthSms]
    going_quiet: int


class ChangelogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    published_at: dt.datetime | None
    created_at: dt.datetime


class ChangelogIn(Strict):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=5000)
    # Leave out to keep it a draft; now or later to publish.
    published_at: dt.datetime | None = None


class ChangelogUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    published_at: dt.datetime | None = None


class GymReferralRead(BaseModel):
    """A gym that sent us another (§16.5, 10.5)."""

    id: uuid.UUID
    referrer_gym_id: uuid.UUID
    referrer_name: str
    referred_gym_id: uuid.UUID
    referred_name: str
    status: str
    created_at: dt.datetime
    ready_at: dt.datetime | None
    note: str | None


class ReferredGym(BaseModel):
    name: str
    status: str
    joined_at: dt.datetime


class MyReferrals(BaseModel):
    """Settings > Subscription: the link to share, and who joined (10.5)."""

    link: str
    free_months: int
    gyms: list[ReferredGym]


# --- platform admins (§7 /admin): the super admin adds the others ------------------


def _long_enough(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Use at least 12 characters for a platform admin.")
    return value


# As scripts.create_platform_admin asks: they can do a lot to every gym.
AdminPassword = Annotated[NewPassword, AfterValidator(_long_enough)]


class PlatformAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    is_super_admin: bool
    # What they may do (app/core/admin_permissions.py); every key for the
    # super admin.
    permissions: list[str]
    is_active: bool
    two_step_enabled: bool
    last_login_at: dt.datetime | None


class PlatformAdminCreate(Strict):
    name: str = Field(min_length=2, max_length=120)
    email: OptionalEmail = None
    phone: OptionalPhone = None
    password: AdminPassword
    permissions: list[str] = []

    @model_validator(mode="after")
    def has_login(self) -> "PlatformAdminCreate":
        if not self.email and not self.phone:
            raise ValueError("Give an email or a phone number to sign in with.")
        return self


class PlatformAdminUpdate(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: OptionalEmail = None
    phone: OptionalPhone = None
    permissions: list[str] | None = None
    is_active: bool | None = None


class AdminPasswordIn(Strict):
    new_password: AdminPassword
