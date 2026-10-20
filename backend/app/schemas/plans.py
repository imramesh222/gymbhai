import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.auth import Strict

# Paisa. Rs 1,00,00,000 is far beyond any gym fee and still fits an int column.
MAX_PAISA = 10_000_000_00

VISITS_FOR_ONE = "A visit pack is for one person: whose visits would they be?"
CHOOSE_CLASSES = "Choose the classes this plan includes."


class AccessWindow(Strict):
    """When an off-peak plan opens the door (§16.4, 9.4), in Nepal time."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # 0 is Monday.
    days: list[int] = Field(min_length=1, max_length=7)
    start: str = Field(alias="from", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(alias="to", pattern=r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")

    @field_validator("days")
    @classmethod
    def weekdays(cls, value: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in value):
            raise ValueError("Days are 0 (Monday) to 6 (Sunday).")
        return sorted(set(value))

    @model_validator(mode="after")
    def in_order(self) -> "AccessWindow":
        if self.end <= self.start:
            raise ValueError("The hours must end after they start.")
        return self


AccessHours = list[AccessWindow]


def stored_hours(hours: AccessHours | None) -> list[dict] | None:
    """As kept in plans/memberships.access_hours: {"days", "from", "to"}."""
    if not hours:
        return None
    return [w.model_dump(by_alias=True) for w in hours]


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    duration_months: int | None
    duration_days: int | None
    price: int | None
    admission_fee: int
    all_branches: bool
    branch_ids: list[uuid.UUID] = []
    is_active: bool
    sort_order: int
    visit_limit: int | None = None
    access_hours: list[dict] | None = None
    # People one sale covers (§19.1).
    seats: int = 1
    # The classes it lets one book (§19.4).
    classes: str = "all"
    class_type_ids: list[uuid.UUID] | None = None


ClassAccess = Literal["none", "all", "chosen"]


class PlanCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    duration_months: int | None = Field(default=None, ge=1, le=60)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    admission_fee: int = Field(default=0, ge=0, le=MAX_PAISA)
    all_branches: bool = True
    branch_ids: list[uuid.UUID] = []
    sort_order: int = 0
    visit_limit: int | None = Field(default=None, ge=1, le=1000)
    access_hours: AccessHours | None = Field(default=None, max_length=14)
    seats: int = Field(default=1, ge=1, le=6)
    classes: ClassAccess = "all"
    class_type_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def one_duration(self) -> "PlanCreate":
        if (self.duration_months is None) == (self.duration_days is None):
            raise ValueError("Give a duration in months or in days.")
        if not self.all_branches and not self.branch_ids:
            raise ValueError("Choose at least one branch.")
        if self.seats > 1 and self.visit_limit is not None:
            raise ValueError(VISITS_FOR_ONE)
        if self.classes == "chosen" and not self.class_type_ids:
            raise ValueError(CHOOSE_CLASSES)
        return self


class PlanUpdate(Strict):
    """Changes apply to memberships sold from now on; sold ones keep their terms."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    duration_months: int | None = Field(default=None, ge=1, le=60)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    admission_fee: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    all_branches: bool | None = None
    branch_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    # Null clears it (unlimited / any time): sent explicitly, so not dropped.
    visit_limit: int | None = Field(default=None, ge=1, le=1000)
    access_hours: AccessHours | None = Field(default=None, max_length=14)
    seats: int | None = Field(default=None, ge=1, le=6)
    classes: ClassAccess | None = None
    class_type_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
