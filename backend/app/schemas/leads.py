"""Enquiries (PLAN.md §16.4, 9.1)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import OptionalEmail, OptionalPhone, Strict

Source = Literal[
    "walk_in", "phone", "facebook", "instagram", "tiktok", "referral", "other"
]
Status = Literal["new", "contacted", "trial", "joined", "lost"]


class LeadIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    phone: OptionalPhone = None
    email: OptionalEmail = None
    source: Source = "walk_in"
    branch_id: uuid.UUID | None = None  # the staff member's first branch if left out
    plan_id: uuid.UUID | None = None
    follow_up_on: dt.date | None = None
    assigned_to: uuid.UUID | None = None
    referred_by_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def some_way_to_reach_them(self) -> "LeadIn":
        if not self.phone and not self.email:
            raise ValueError("Enter a mobile number or an email, to follow up.")
        return self


class LeadUpdate(Strict):
    """Joined is not set here: Convert does that, with the member it made."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: OptionalPhone = None
    email: OptionalEmail = None
    source: Source | None = None
    branch_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    status: Literal["new", "contacted", "trial", "lost"] | None = None
    follow_up_on: dt.date | None = None
    lost_reason: str | None = Field(default=None, max_length=200)
    assigned_to: uuid.UUID | None = None
    referred_by_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    source: str
    plan_id: uuid.UUID | None
    status: str
    follow_up_on: dt.date | None
    lost_reason: str | None
    assigned_to: uuid.UUID | None
    trial_on: dt.date | None
    referred_by_id: uuid.UUID | None
    member_id: uuid.UUID | None
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    plan_name: str | None = None
    assigned_name: str | None = None
    referred_by_name: str | None = None


class LeadMatch(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["member", "lead"]
    # A member's code, or an enquiry's status.
    detail: str


class SourceRow(BaseModel):
    source: str
    enquiries: int
    trials: int
    joined: int
    # Joined out of enquiries; None with no enquiries.
    conversion: float | None


class Referrer(BaseModel):
    member_id: uuid.UUID
    name: str
    member_code: str
    referred: int
    joined: int


class LeadReport(BaseModel):
    """Enquiries made in [from, to], and what became of them."""

    first_day: dt.date
    last_day: dt.date
    rows: list[SourceRow]
    total: SourceRow
    top_referrers: list[Referrer] = []
