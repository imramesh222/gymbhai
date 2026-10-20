"""Progress (PLAN.md §19.5). Whole numbers: grams, tenths of a percent, mm."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import Strict

MEASURES = (
    "weight_g",
    "body_fat",
    "chest_mm",
    "waist_mm",
    "hips_mm",
    "arm_mm",
    "thigh_mm",
)
Mm = Field(default=None, ge=100, le=2500)


class EntryFields(Strict):
    measured_on: dt.date | None = None
    weight_g: int | None = Field(default=None, ge=20_000, le=300_000)
    body_fat: int | None = Field(default=None, ge=10, le=700)
    chest_mm: int | None = Mm
    waist_mm: int | None = Mm
    hips_mm: int | None = Mm
    arm_mm: int | None = Mm
    thigh_mm: int | None = Mm
    note: str | None = Field(default=None, max_length=500)


class EntryIn(EntryFields):
    @model_validator(mode="after")
    def something(self) -> "EntryIn":
        if all(getattr(self, m) is None for m in MEASURES):
            raise ValueError("Enter a weight or a measurement.")
        return self


class EntryUpdate(EntryFields):
    """Only what's given changes; a null clears that measurement."""


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    measured_on: dt.date
    weight_g: int | None
    body_fat: int | None
    chest_mm: int | None
    waist_mm: int | None
    hips_mm: int | None
    arm_mm: int | None
    thigh_mm: int | None
    note: str | None
    # By staff (their name), or by the member (null).
    recorded_by_name: str | None = None
    created_at: dt.datetime


class PhotoRead(BaseModel):
    id: uuid.UUID
    taken_on: dt.date
    pose: str
    url: str
    shared: bool


class ProgressRead(BaseModel):
    height_mm: int | None
    entries: list[EntryRead]
    # The member's own, or (for staff) only what they shared with their trainer.
    photos: list[PhotoRead]


class HeightIn(Strict):
    height_mm: int | None = Field(ge=500, le=2500)


class PhotoUpdate(Strict):
    shared: bool


Pose = Literal["front", "side", "back"]
