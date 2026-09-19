import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import OptionalEmail, Strict
from app.schemas.messaging import NoticeRead
from app.schemas.money import PaymentMethodRead, PaymentRead
from app.schemas.plans import PlanRead


class PublicBranch(BaseModel):
    id: uuid.UUID
    name: str


class PublicGym(BaseModel):
    """What the member app shows before sign-in; nothing private."""

    slug: str
    name: str
    logo_url: str | None
    brand_color: str | None
    date_display: str
    branches: list[PublicBranch]


class CodeRequest(Strict):
    phone: str | None = Field(default=None, max_length=20)
    email: OptionalEmail = None


class CodeRequested(BaseModel):
    channel: str
    sent_to: str
    expires_in: int


class CodeVerify(CodeRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    # When several members share the phone: which one is signing in.
    member_id: uuid.UUID | None = None


class MemberChoice(BaseModel):
    id: uuid.UUID
    name: str


class QrIdentity(BaseModel):
    """What the phone needs to draw its own changing QR, offline (§4.2)."""

    member_hex: str
    key: str
    version: int
    window_seconds: int


class MemberState(BaseModel):
    status: str
    plan_name: str | None
    valid_until: dt.date | None
    days_left: int
    dues: int


class MemberMe(BaseModel):
    id: uuid.UUID
    name: str
    member_code: str
    phone: str
    email: str | None
    photo_url: str | None
    home_branch_id: uuid.UUID
    state: MemberState
    qr: QrIdentity
    gym: PublicGym
    visits_this_month: int
    streak_weeks: int
    latest_notice: NoticeRead | None


class MemberSignIn(BaseModel):
    """Either signed in, or "who are you?" for a shared phone."""

    access_token: str | None = None
    expires_in: int | None = None
    me: MemberMe | None = None
    choose: list[MemberChoice] | None = None


class Visit(BaseModel):
    at: dt.datetime
    result: str
    branch_name: str | None


class MemberPayments(BaseModel):
    dues: int
    payments: list[PaymentRead]
    requests: list["PaymentRequestRead"]


class PaymentRequestIn(Strict):
    plan_id: uuid.UUID
    payment_method_id: uuid.UUID | None = None
    amount: int = Field(gt=0, le=10_000_000_00)
    transaction_ref: str | None = Field(default=None, max_length=64)


class PaymentRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    plan_id: uuid.UUID
    payment_method_id: uuid.UUID | None
    amount: int
    transaction_ref: str | None
    screenshot_url: str | None = None
    status: str
    reject_reason: str | None
    reviewed_at: dt.datetime | None
    membership_id: uuid.UUID | None
    created_at: dt.datetime
    plan_name: str | None = None
    method_label: str | None = None
    member_name: str | None = None
    member_code: str | None = None
    expected_total: int | None = None
    reviewed_by_name: str | None = None


class RenewOptions(BaseModel):
    plans: list[PlanRead]
    payment_methods: list[PaymentMethodRead]
    renewal_starts_on: dt.date
    first_membership: bool


class ApproveIn(Strict):
    price: int | None = Field(default=None, ge=0, le=10_000_000_00)
    discount: int = Field(default=0, ge=0, le=10_000_000_00)
    accept_part_payment: bool = False


class RejectIn(Strict):
    reason: str = Field(min_length=3, max_length=300)


# --- door ------------------------------------------------------------------------


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    last_seen_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime


class DeviceIn(Strict):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)


class DeviceRegistered(BaseModel):
    device: DeviceRead
    # Shown once: the kiosk keeps it; we keep only its hash.
    token: str


class KioskMe(BaseModel):
    device: DeviceRead
    branch_name: str
    gym: PublicGym


class ScanIn(Strict):
    code: str = Field(min_length=4, max_length=200)


class StaffScanIn(ScanIn):
    branch_id: uuid.UUID


class ManualCheckIn(Strict):
    member_id: uuid.UUID
    branch_id: uuid.UUID
    override: bool = False
    note: str | None = Field(default=None, max_length=300)


class ScanResult(BaseModel):
    """What the door shows for 3 seconds (§4.3)."""

    result: str  # allowed, warned, duplicate, override, denied_*, unknown
    let_in: bool
    reason: str | None = None
    check_in_id: uuid.UUID | None = None
    member_id: uuid.UUID | None = None
    member_name: str | None = None
    member_code: str | None = None
    photo_url: str | None = None
    plan_name: str | None = None
    days_left: int = 0
    valid_until: dt.date | None = None
    dues: int = 0
    # Staff can override a denial when they hold door.override.
    can_override: bool = False


class CheckInRead(BaseModel):
    id: uuid.UUID
    at: dt.datetime
    member_id: uuid.UUID
    member_name: str
    member_code: str
    branch_id: uuid.UUID
    method: str
    result: str
    staff_name: str | None
    note: str | None


class CheckInList(BaseModel):
    items: list[CheckInRead]
    total: int


class AttendanceSummary(BaseModel):
    by_day: dict[str, int]
    by_hour: dict[int, int]
    denied: int
    let_in: int
    unique_members: int


# --- member access (staff) -----------------------------------------------------------


class AccessIn(Strict):
    app_access: bool


class CardRead(BaseModel):
    member_id: uuid.UUID
    member_code: str
    name: str
    photo_url: str | None
    card_code: str
    gym_name: str
    logo_url: str | None
