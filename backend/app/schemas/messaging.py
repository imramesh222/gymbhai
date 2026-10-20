import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.messaging import (
    TRIGGER_BIRTHDAY,
    TRIGGER_DUES,
    TRIGGER_EXPIRY,
    TRIGGER_LAPSED,
    TRIGGER_NOT_VISITING,
    TRIGGER_PROGRESS,
    TRIGGER_PT_DUES,
    TRIGGER_PT_ENDING,
)
from app.schemas.auth import Strict
from app.schemas.members import MemberRead

Trigger = Literal[
    "expiry",
    "lapsed",
    "dues",
    "not_visiting",
    "birthday",
    "pt_ending",
    "pt_dues",
    "progress",
]

# The days each trigger accepts (PLAN.md §16.3, 8.2).
DAYS_ALLOWED: dict[str, tuple[int, int]] = {
    TRIGGER_EXPIRY: (-60, 60),
    TRIGGER_LAPSED: (1, 365),
    TRIGGER_DUES: (1, 90),
    TRIGGER_NOT_VISITING: (3, 180),
    TRIGGER_BIRTHDAY: (0, 0),
    TRIGGER_PT_ENDING: (-60, 60),
    TRIGGER_PT_DUES: (1, 90),
    TRIGGER_PROGRESS: (7, 180),
}


def check_days(trigger: str, days: int) -> None:
    low, high = DAYS_ALLOWED[trigger]
    if not low <= days <= high:
        raise ValueError(f"Days must be from {low} to {high} for this automation.")


class PtOwing(BaseModel):
    """Personal training with money still owed on it (§18.3)."""

    package_id: uuid.UUID
    member_id: uuid.UUID
    name: str
    phone: str
    plan_name: str
    trainer_name: str
    end_date: dt.date
    dues: int


class FollowUpLists(BaseModel):
    """PLAN.md §16.3, 8.1: who to chase. Owing and not visiting show the first
    100; the totals say how many there are."""

    due_today: list[MemberRead]
    due_this_week: list[MemberRead]
    lapsed: list[MemberRead]
    owing: list[MemberRead]
    owing_total: int
    # Owed on personal training, apart from memberships (§18.3).
    pt_owing: list[PtOwing]
    pt_owing_total: int
    not_visiting: list[MemberRead]
    not_visiting_total: int
    not_visiting_days: int


class SmsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID | None
    to: str
    body: str
    kind: str
    status: str
    segments: int
    error: str | None
    sent_at: dt.datetime | None
    created_at: dt.datetime


class SmsLog(BaseModel):
    balance: int
    items: list[SmsRead]


class BulkSmsIn(Strict):
    """One message to the members picked on the Members list."""

    member_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=640)


class BulkSmsResult(BaseModel):
    queued: int


MessagePurpose = Literal["reminder", "dues", "not_visiting", "welcome", "pt_dues"]


class MemberMessage(BaseModel):
    """The gym's wording filled in for one member, for the desk to send from
    its own phone on WhatsApp (§18.5). Nothing is sent by us."""

    text: str
    # As stored, 98XXXXXXXX: the screen adds Nepal's 977 for WhatsApp.
    phone: str


class MemberSmsIn(Strict):
    """Either the gym's reminder wording, or a message typed at the desk."""

    reminder: bool = False
    body: str | None = Field(default=None, min_length=1, max_length=640)

    @model_validator(mode="after")
    def one_or_other(self) -> "MemberSmsIn":
        if not self.reminder and not self.body:
            raise ValueError("Write a message, or send the reminder.")
        return self


class ReminderRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: Trigger
    days: int
    template: str
    enabled: bool


class ReminderRuleIn(Strict):
    trigger: Trigger = TRIGGER_EXPIRY
    days: int
    template: str = Field(min_length=5, max_length=640)
    enabled: bool = True

    @model_validator(mode="after")
    def days_in_range(self) -> "ReminderRuleIn":
        check_days(self.trigger, self.days)
        return self


class ReminderRuleUpdate(Strict):
    """The trigger stays: a different trigger is a different automation."""

    days: int | None = None
    template: str | None = Field(default=None, min_length=5, max_length=640)
    enabled: bool | None = None


class SmsTemplates(BaseModel):
    welcome_sms: str
    membership_sms: str
    # SMS as well as push, for members whose phone takes push (§16.3, 8.3).
    also_sms: bool


class SmsTemplatesUpdate(Strict):
    welcome_sms: str | None = Field(default=None, min_length=5, max_length=640)
    membership_sms: str | None = Field(default=None, min_length=5, max_length=640)
    also_sms: bool | None = None


class NoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID | None
    title: str
    body: str
    published_at: dt.datetime
    send_sms: bool
    sms_count: int
    push_count: int


class NoticeIn(Strict):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    branch_id: uuid.UUID | None = None
    send_sms: bool = False


class NoticeCost(BaseModel):
    recipients: int
    by_push: int
    by_sms: int
    segments_each: int
    total_credits: int
    balance: int
