import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.gym_settings import DateDisplay, DuesRule, PlanMonths
from app.schemas.auth import OptionalPhone, Strict

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class GymSettingsUpdate(Strict):
    plan_months: PlanMonths | None = None
    date_display: DateDisplay | None = None
    member_code_prefix: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,5}$")
    daily_summary_sms: bool | None = None


class CheckInRulesUpdate(Strict):
    """Door rules (§4.3, §5.3) — a permission of their own (§2.1)."""

    dues_rule: DuesRule | None = None
    grace_days: int | None = Field(default=None, ge=0, le=30)
    rescan_minutes: int | None = Field(default=None, ge=0, le=24 * 60)


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
