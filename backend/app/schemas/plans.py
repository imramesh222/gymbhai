import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import Strict

# Paisa. Rs 1,00,00,000 is far beyond any gym fee and still fits an int column.
MAX_PAISA = 10_000_000_00


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


class PlanCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    duration_months: int | None = Field(default=None, ge=1, le=60)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    admission_fee: int = Field(default=0, ge=0, le=MAX_PAISA)
    all_branches: bool = True
    branch_ids: list[uuid.UUID] = []
    sort_order: int = 0

    @model_validator(mode="after")
    def one_duration(self) -> "PlanCreate":
        if (self.duration_months is None) == (self.duration_days is None):
            raise ValueError("Give a duration in months or in days.")
        if not self.all_branches and not self.branch_ids:
            raise ValueError("Choose at least one branch.")
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
