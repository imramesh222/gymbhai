import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.auth import Strict


class Person(BaseModel):
    member_id: uuid.UUID
    name: str
    at: dt.datetime
    result: str | None = None


class TodayRead(BaseModel):
    date: dt.date
    check_ins: int
    unique_visitors: int
    inside_now: list[Person]
    due_today: int
    expiring_this_week: int
    turned_away: list[Person]
    members_with_dues: int
    dues_total: int
    active_members: int
    # Only for staff who may see money (reports.money).
    collected: int | None
    collected_by_method: dict[str, int] | None
    # Only for staff who approve app payments.
    pending_requests: int | None


class MonthlyRead(BaseModel):
    month: str
    calendar: str
    first_day: dt.date
    last_day: dt.date
    income: int
    income_by_method: dict[str, int]
    new_members: int
    new_memberships: int
    renewals: int
    lapsed: int
    due_to_renew: int
    renewed: int
    renewal_rate: float | None
    active_members: int
    visits: int
    by_plan: dict[str, int]


class ImportPreview(BaseModel):
    id: uuid.UUID
    filename: str
    headers: list[str]
    mapping: dict[str, int | None]
    total_rows: int
    sample: list[list[Any]]
    # First problems found with this mapping: row number (1 = first data row).
    problems: list[tuple[int, str]]
    ready: int
    status: str
    result: dict[str, Any] | None = None


class ImportCommit(Strict):
    mapping: dict[str, int | None] = Field(default_factory=dict)
    # Skip rows whose phone and name are already a member here.
    skip_existing: bool = True
