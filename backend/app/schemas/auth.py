import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

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

from app.core.gym_settings import GymSettings
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


def _not_obvious(value: str) -> str:
    if value.lower() in OBVIOUS_PASSWORDS:
        raise ValueError("Choose a less predictable password.")
    return value


# Any password a person chooses: at sign-up, on a change, after a reset.
NewPassword = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=72),
    AfterValidator(_not_obvious),
]

Phone = Annotated[str, AfterValidator(normalize_phone)]
OptionalPhone = Annotated[Phone | None, BeforeValidator(_blank_to_none)]
OptionalEmail = Annotated[
    EmailStr | None, BeforeValidator(_blank_to_none), AfterValidator(_lower)
]


class GymSignup(Strict):
    gym_name: str = Field(min_length=2, max_length=120)
    slug: str
    branch_name: str = Field(default="Main branch", min_length=1, max_length=120)
    owner_name: str = Field(min_length=2, max_length=120)
    owner_phone: OptionalPhone = None
    owner_email: OptionalEmail = None
    password: NewPassword
    # The terms of service and privacy policy (app/core/legal.py).
    accept_terms: bool
    # The language the gym starts in (§16.6): its staff, members and SMS.
    language: Literal["en", "ne"] = "en"
    # The address of the gym that sent them: /signup?ref=... (§16.5, 10.5).
    ref: str | None = Field(default=None, max_length=60)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        return check_slug(value)

    @field_validator("accept_terms")
    @classmethod
    def terms_accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Accept the terms and privacy policy to continue.")
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


class PasswordResetRequest(Strict):
    identifier: str = Field(min_length=3, max_length=254)


class PasswordResetConfirm(Strict):
    identifier: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: NewPassword


class TwoStepChallenge(BaseModel):
    """The password was right; now the code from the authenticator app."""

    two_step_token: str
    expires_in: int


class TwoStepLogin(Strict):
    two_step_token: str = Field(min_length=1, max_length=2000)
    # Six digits from the app, or a recovery code like "abcd-efgh".
    code: str = Field(min_length=6, max_length=20)


class PasswordConfirm(Strict):
    """Turning two-step sign-in on or off, or new recovery codes, needs the
    password again: a token lifted from a desk PC must not be enough."""

    password: str = Field(min_length=1, max_length=200)


class TwoStepSetupRead(BaseModel):
    # For typing into the app by hand; `uri` goes in the QR code.
    secret: str
    uri: str


class TwoStepEnable(Strict):
    code: str = Field(min_length=6, max_length=10)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


class TwoStepStatus(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_left: int


class DeviceSession(BaseModel):
    """A device signed in to your account (My account → Devices)."""

    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_used_at: datetime | None
    current: bool


class SignedOut(BaseModel):
    signed_out: int


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
    # GymBhai can send WhatsApp messages (§19.3): until it can, the gym's
    # "Send messages by WhatsApp" stays off.
    whatsapp_available: bool = False


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
    is_super_admin: bool
    last_login_at: datetime | None
    two_step_enabled: bool


class Me(BaseModel):
    staff: StaffRead
    gym: GymRead | None
    # Must use two-step sign-in. With it not yet enabled, only setting it up
    # works (§16.1).
    two_step_required: bool
    permissions: list[str]
    # None means every branch.
    branch_ids: list[uuid.UUID] | None
    subscription: SubscriptionRead | None
    # Help (§16.5, 10.3): our WhatsApp/Viber number, if set.
    support_whatsapp: str | None = None
    # What's new has an entry they haven't opened (10.4).
    changelog_unread: bool = False
    # The language to show (§16.6): their own choice, else the gym's.
    language: Literal["en", "ne"] = "en"
    # Their own choice; null follows the gym.
    own_language: Literal["en", "ne"] | None = None
    # With Nepali: ०१२ or 012, as the gym chose.
    digits: Literal["nepali", "western"] = "western"


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Seconds until the access token expires. Refresh before, or on a 401.
    expires_in: int
    me: Me


class LanguageIn(Strict):
    """Null goes back to the gym's language."""

    language: Literal["en", "ne"] | None


# --- notifications for staff (PLAN.md §18.6) ---------------------------------------

NotificationKind = Literal["payment_request", "freeze_request", "lead"]


class StaffPushStatus(BaseModel):
    """My account → Notifications."""

    # None: push isn't set up on this server.
    public_key: str | None
    # This browser, for this sign-in.
    on_here: bool
    # What this person may get, in order, and which of those they turned off.
    kinds: list[NotificationKind]
    muted: list[NotificationKind]


class StaffPushEndpoint(Strict):
    """Which browser: the endpoint its PushManager gave."""

    endpoint: str = Field(min_length=10, max_length=2000)


class NotificationsIn(Strict):
    """The ticks, as what's turned off; `endpoint` for the answer's `on_here`."""

    muted: list[NotificationKind] = Field(max_length=10)
    endpoint: str | None = Field(default=None, min_length=10, max_length=2000)
