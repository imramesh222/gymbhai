"""Expenses (PLAN.md §18.1)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import Strict
from app.schemas.money import Method

Category = Literal[
    "rent",
    "salaries",
    "electricity",
    "water",
    "internet",
    "equipment",
    "repairs",
    "cleaning",
    "marketing",
    "fees",
    "other",
]


class ExpenseIn(Strict):
    category: Category
    amount: int = Field(gt=0, le=10_000_000_00)
    # Today in Nepal if left out; never after today.
    spent_on: dt.date | None = None
    method: Method = "cash"
    paid_to: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    # None is the whole gym, for staff who work at every branch.
    branch_id: uuid.UUID | None = None


class ExpenseUpdate(Strict):
    """Only what is sent changes; `"branch_id": null` makes it the whole gym's."""

    category: Category | None = None
    amount: int | None = Field(default=None, gt=0, le=10_000_000_00)
    spent_on: dt.date | None = None
    method: Method | None = None
    paid_to: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    branch_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID | None
    category: str
    amount: int
    spent_on: dt.date
    method: str
    paid_to: str | None
    note: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None = None
    created_at: dt.datetime
    voided_at: dt.datetime | None
    void_reason: str | None


class ExpenseList(BaseModel):
    """A month of the gym's own calendar: BS months for a gym showing BS."""

    month: str
    calendar: str
    first_day: dt.date
    last_day: dt.date
    items: list[ExpenseRead]
    # Over the whole month (and category, if asked), voided ones left out.
    sum_amount: int
    by_category: dict[str, int]
