import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import Strict
from app.schemas.members import MemberRead


class ExpiringLists(BaseModel):
    """PLAN.md §7, Expiring: due in 7 days, due today, lapsed in the last 30."""

    due_today: list[MemberRead]
    due_this_week: list[MemberRead]
    lapsed: list[MemberRead]


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
    days_from_expiry: int
    template: str
    enabled: bool


class ReminderRuleIn(Strict):
    days_from_expiry: int = Field(ge=-60, le=60)
    template: str = Field(min_length=5, max_length=640)
    enabled: bool = True


class ReminderRuleUpdate(Strict):
    days_from_expiry: int | None = Field(default=None, ge=-60, le=60)
    template: str | None = Field(default=None, min_length=5, max_length=640)
    enabled: bool | None = None


class SmsTemplates(BaseModel):
    welcome_sms: str
    membership_sms: str


class SmsTemplatesUpdate(Strict):
    welcome_sms: str | None = Field(default=None, min_length=5, max_length=640)
    membership_sms: str | None = Field(default=None, min_length=5, max_length=640)


class NoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID | None
    title: str
    body: str
    published_at: dt.datetime
    send_sms: bool
    sms_count: int


class NoticeIn(Strict):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    branch_id: uuid.UUID | None = None
    send_sms: bool = False


class NoticeCost(BaseModel):
    recipients: int
    segments_each: int
    total_credits: int
    balance: int
