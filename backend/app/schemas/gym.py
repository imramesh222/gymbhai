import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.gym_settings import DateDisplay, DuesRule, PlanMonths
from app.schemas.auth import OptionalPhone, Strict

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class GymSettingsUpdate(Strict):
    plan_months: PlanMonths | None = None
    date_display: DateDisplay | None = None
    member_code_prefix: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,5}$")
    daily_summary_sms: bool | None = None
    poster_printed: bool | None = None
    setup_dismissed: bool | None = None
    show_busyness: bool | None = None
    join_form: bool | None = None
    # WhatsApp messages to members who agree (§19.3).
    whatsapp: bool | None = None
    language: Literal["en", "ne"] | None = None
    digits: Literal["nepali", "western"] | None = None


class CheckInRulesUpdate(Strict):
    """Door rules (§4.3, §5.3) — a permission of their own (§2.1)."""

    dues_rule: DuesRule | None = None
    grace_days: int | None = Field(default=None, ge=0, le=30)
    rescan_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    # Follow up's "not visiting" (§16.3, 8.1).
    not_visiting_days: int | None = Field(default=None, ge=3, le=90)
    # The kiosk offline (§19.2).
    kiosk_offline_days: int | None = Field(default=None, ge=1, le=7)


class ClassRulesUpdate(Strict):
    """Booking classes (§19.4): with Manage classes."""

    class_booking_days: int | None = Field(default=None, ge=1, le=30)
    class_closes_minutes: int | None = Field(default=None, ge=0, le=240)
    class_cancel_hours: int | None = Field(default=None, ge=0, le=48)
    no_show_limit: int | None = Field(default=None, ge=0, le=10)
    no_show_block_days: int | None = Field(default=None, ge=1, le=30)


class SecurityUpdate(Strict):
    """Settings → Security: the owner's alone (PATCH /gym/security)."""

    require_two_step: bool


class GymUpdate(Strict):
    """Settings → Gym profile. The slug is not here: it is printed on posters."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: OptionalPhone = None
    address: str | None = Field(default=None, max_length=255)
    brand_color: HexColor | None = None
    settings: GymSettingsUpdate | None = None

    @field_validator("name")
    @classmethod
    def name_not_null(cls, value: str | None) -> str:
        # Leaving it out keeps the name; sending null is a mistake, not a clear.
        if value is None:
            raise ValueError("The gym needs a name.")
        return value


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    is_active: bool


class BranchCreate(Strict):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: OptionalPhone = None


class BranchUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: OptionalPhone = None
    is_active: bool | None = None
