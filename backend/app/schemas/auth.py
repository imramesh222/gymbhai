import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.gym_settings import DateDisplay, GymSettings, PlanMonths
from app.core.phone import normalize_phone
from app.core.slugs import check_slug

MIN_PASSWORD_LENGTH = 8
# Refused however long they are: the ones a busy gym desk actually picks.
OBVIOUS_PASSWORDS = {"password", "password1", "12345678", "123456789", "1234567890"}


class Strict(BaseModel):
    """Unknown fields are an error, not ignored.

    Above all this stops a `gym_id` in a request body from being quietly
    accepted: the gym only ever comes from the token.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _blank_to_none(value: Any) -> Any:
    """Forms send "" for an optional field left empty."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _lower(value: str | None) -> str | None:
    return value.lower() if value else value


Phone = Annotated[str, AfterValidator(normalize_phone)]
OptionalPhone = Annotated[Phone | None, BeforeValidator(_blank_to_none)]
OptionalEmail = Annotated[
    EmailStr | None, BeforeValidator(_blank_to_none), AfterValidator(_lower)
]


class GymSignup(Strict):
    gym_name: str = Field(min_length=2, max_length=120)
    slug: str
    branch_name: str = Field(default="Main branch", min_length=1, max_length=120)
    # No defaults: the owner must choose (PLAN.md §5.1).
    plan_months: PlanMonths
    date_display: DateDisplay
    owner_name: str = Field(min_length=2, max_length=120)
    owner_phone: OptionalPhone = None
    owner_email: OptionalEmail = None
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=72)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        return check_slug(value)

    @field_validator("password")
    @classmethod
    def not_obvious(cls, value: str) -> str:
        if value.lower() in OBVIOUS_PASSWORDS:
            raise ValueError("Choose a less predictable password.")
        return value

    @model_validator(mode="after")
    def has_login(self) -> "GymSignup":
        if not self.owner_phone and not self.owner_email:
            raise ValueError("Give a phone number or an email to sign in with.")
        return self


class LoginRequest(Strict):
    # An email address or a phone number, in any common format.
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class GymRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    phone: str | None
    address: str | None
    logo_url: str | None = None
    brand_color: str | None
    status: str
    settings: GymSettings


class SubscriptionRead(BaseModel):
    status: str
    plan_name: str | None = None
    starts_on: date | None
    ends_on: date | None
    # Including today; 0 once it has ended.
    days_left: int
    # ok, ending (a week or less left), grace, read_only (PLAN.md §5.7).
    phase: str = "ok"
    grace_ends_on: date | None = None
    over_limit: bool = False


class StaffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    is_owner: bool
    is_platform_admin: bool
    last_login_at: datetime | None


class Me(BaseModel):
    staff: StaffRead
    gym: GymRead | None
    permissions: list[str]
    # None means every branch.
    branch_ids: list[uuid.UUID] | None
    subscription: SubscriptionRead | None


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Seconds until the access token expires. Refresh before, or on a 401.
    expires_in: int
    me: Me
