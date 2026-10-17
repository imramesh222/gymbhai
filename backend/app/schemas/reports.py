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


class MemberBrief(BaseModel):
    member_id: uuid.UUID
    name: str
    phone: str


class MemberOwing(BaseModel):
    member_id: uuid.UUID
    name: str
    dues: int


class SetupChecklist(BaseModel):
    """What a new gym still has to do (§16.2, 7.4). True means done."""

    plans_priced: bool
    payment_account: bool
    logo: bool
    staff_invited: bool
    poster_printed: bool
    first_member: bool


class LeadDue(BaseModel):
    lead_id: uuid.UUID
    name: str
    phone: str | None
    status: str
    follow_up_on: dt.date


class TodayRead(BaseModel):
    date: dt.date
    check_ins: int
    # Let in, by hour of the day in Nepal: 24 counts.
    check_ins_by_hour: list[int]
    # Yesterday up to this same time of day, so the two compare fairly.
    check_ins_yesterday: int
    # The to-do list: who ends today (to call or remind), who owes most.
    ending_today: list[MemberBrief]
    top_owing: list[MemberOwing]
    unique_visitors: int
    inside_now: list[Person]
    due_today: int
    expiring_this_week: int
    # Active, but no visit for the gym's "not visiting" days (§16.3, 8.1).
    not_visiting: int
    turned_away: list[Person]
    members_with_dues: int
    dues_total: int
    active_members: int
    # Only for staff who may see money (reports.money).
    collected: int | None
    collected_by_method: dict[str, int] | None
    collected_yesterday: int | None
    # Only for staff who approve app payments.
    pending_requests: int | None
    # Only for staff who set the gym up, until it is done or put away.
    setup: SetupChecklist | None
    # Enquiries to follow up today or overdue; only with Enquiries (9.1).
    leads_due: int | None = None
    leads_due_list: list[LeadDue] = []


class TrendMonth(BaseModel):
    month: str
    # False for months that ended before the gym joined: charts show a gap.
    started: bool
    income: int
    new_members: int
    renewals: int
    lapsed: int
    active_members: int
    visits: int
    renewal_rate: float | None


class TrendRead(BaseModel):
    calendar: str
    months: list[TrendMonth]


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
