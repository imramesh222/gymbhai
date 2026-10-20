import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.auth import OptionalEmail, Strict
from app.schemas.messaging import NoticeRead
from app.schemas.money import PaymentMethodRead, PaymentRead
from app.schemas.plans import PlanRead
from app.schemas.training import MemberTraining


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
    # "Not a member yet? Ask to join" (§16.4, 9.5).
    join_form: bool = False


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
    # "app": the phone app (PLAN.md §17.2) gets its refresh token in the
    # answer, to keep in secure storage; the web gets an httpOnly cookie.
    client: Literal["web", "app"] = "web"


class DeskSignIn(Strict):
    """The QR shown at the desk (PLAN.md §18.4), instead of a code."""

    token: str = Field(min_length=16, max_length=64)
    client: Literal["web", "app"] = "web"


class MemberChoice(BaseModel):
    id: uuid.UUID
    name: str


class QrIdentity(BaseModel):
    """What the phone needs to draw its own changing QR, offline (§4.2)."""

    member_hex: str
    key: str
    version: int
    window_seconds: int
    # Ed25519, for gb2 codes a kiosk can check offline (§19.2).
    signing_key: str | None = None


class MemberState(BaseModel):
    status: str
    plan_name: str | None
    valid_until: dt.date | None
    days_left: int
    dues: int
    # A visit pack: "7 of 10 visits left"; off-peak: when they may come (9.3, 9.4).
    visit_limit: int | None = None
    visits_left: int | None = None
    access_hours: list[dict] | None = None
    # A family or couple plan (§19.1): the others on it, and who pays when
    # it isn't them ("Ram pays for this"), with what's still owed on it.
    plan_with: list[str] = []
    paid_by: str | None = None
    group_dues: int = 0


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
    emergency_contact: str | None = None
    # "quiet", "normal" or "busy" at their branch now; None if the gym hides it
    # or it's too new to tell (§16.3, 8.5).
    busy: Literal["quiet", "normal", "busy"] | None = None
    # The app's language (§16.6): their own choice, else the gym's.
    language: Literal["en", "ne"] = "en"
    own_language: Literal["en", "ne"] | None = None
    digits: Literal["nepali", "western"] = "western"
    # Personal training still to come or under way, soonest first (§18.3).
    training: list[MemberTraining] = []
    # Classes at their branch in the next week: Home offers to book (§19.4).
    has_classes: bool = False


class MemberSignIn(BaseModel):
    """Either signed in, or "who are you?" for a shared phone."""

    access_token: str | None = None
    expires_in: int | None = None
    me: MemberMe | None = None
    choose: list[MemberChoice] | None = None
    # The phone app only (§17.2): a new one at every refresh, the old one
    # then dead. Never sent to the web, which has the cookie.
    refresh_token: str | None = None


class AppSession(Strict):
    """The phone app's refresh and sign-out (§17.2): the token in the body."""

    refresh_token: str = Field(min_length=20, max_length=200)


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
    # A family or couple plan's others (§19.1).
    with_names: list[str] = []


class RenewMate(BaseModel):
    id: uuid.UUID
    name: str
    first_membership: bool


class RenewOptions(BaseModel):
    plans: list[PlanRead]
    payment_methods: list[PaymentMethodRead]
    renewal_starts_on: dt.date
    first_membership: bool
    # Whoever pays for a family or couple plan renews it for these people too
    # (§19.1); a plan for several is offered only then, and only if they fit.
    renew_with: list[RenewMate] = []


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
    # "kiosk", or a reader: "zkteco" or "hikvision" (§18.2).
    kind: str = "kiosk"
    serial: str | None = None
    last_seen_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime
    # A reader's members on it, and changes not yet made there.
    on_reader: int | None = None
    waiting: int | None = None


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


# --- the kiosk offline (PLAN.md §19.2) ---


class RosterMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    # Changes with the photo, so the kiosk knows to fetch it again.
    photo: str | None
    photo_url: str | None
    # SHA-256 of their card's token; their gb2 public key.
    card: str
    key: str
    # One letter a day from the roster's `from_date` (app/services/kiosk.py).
    days: str
    hours: list[dict] | None
    visits_left: int | None
    owes: bool
    plan_name: str | None
    valid_until: dt.date | None


class KioskRules(BaseModel):
    grace_days: int
    rescan_minutes: int
    dues_rule: str


class KioskRoster(BaseModel):
    branch_id: uuid.UUID
    from_date: dt.date
    # The kiosk keeps its offset from this, and uses our clock offline.
    server_time: dt.datetime
    offline_days: int
    rules: KioskRules
    members: list[RosterMember]


class OfflineScanIn(Strict):
    client_id: str = Field(min_length=8, max_length=64)
    member_id: uuid.UUID
    method: Literal["app_qr", "card_qr"]
    at: dt.datetime
    result: str = Field(max_length=24)


class OfflineScansIn(Strict):
    scans: list[OfflineScanIn] = Field(max_length=500)


class OfflineScansResult(BaseModel):
    recorded: int


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
    # A visit pack: visits left after this one (§16.4, 9.3).
    visits_left: int | None = None
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
    # When the gym is busy: [weekday][hour], Sunday first (Nepal's week).
    by_weekday_hour: list[list[int]]
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


class PushKeys(Strict):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscriptionIn(Strict):
    """What the browser's PushManager.subscribe() gives (§16.3, 8.3)."""

    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    keys: PushKeys


EXPO_TOKEN = r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,200}\]$"


class AppPushIn(Strict):
    """What the phone app's getExpoPushTokenAsync() gives (§17.6)."""

    kind: Literal["expo"]
    expo_token: str = Field(max_length=255, pattern=EXPO_TOKEN)


class PushEndpoint(Strict):
    """Which phone to turn off: a browser's endpoint or the app's token."""

    endpoint: str | None = Field(default=None, min_length=10, max_length=2000)
    expo_token: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _one(self) -> "PushEndpoint":
        if self.endpoint is None and self.expo_token is None:
            raise ValueError("Give the endpoint or the app's token.")
        return self


class PushStatus(BaseModel):
    """For "Get reminders on this phone": None means push isn't set up here."""

    public_key: str | None
    # This phone, if the app sent its endpoint; else any of the member's.
    subscribed: bool


class MyDetailsIn(Strict):
    """What a member changes in their app; the email goes through a code."""

    emergency_contact: str | None = Field(default=None, max_length=120)
    # Null follows the gym's language (§16.6).
    language: Literal["en", "ne"] | None = None


class EmailChangeIn(Strict):
    email: EmailStr


class EmailConfirmIn(Strict):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class FreezeRequestIn(Strict):
    from_date: dt.date
    to_date: dt.date
    reason: str = Field(min_length=3, max_length=500)


class FreezeRequestRead(BaseModel):
    """PLAN.md §16.3, 8.6. Names are filled in for staff."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    membership_id: uuid.UUID
    from_date: dt.date
    to_date: dt.date
    reason: str
    status: str
    reject_reason: str | None
    created_at: dt.datetime
    reviewed_at: dt.datetime | None
    member_name: str | None = None
    member_code: str | None = None
    plan_name: str | None = None
    ends_on: dt.date | None = None
    reviewed_by_name: str | None = None


class JoinPlan(BaseModel):
    id: uuid.UUID
    name: str
    price: int | None


class JoinOptions(BaseModel):
    plans: list[JoinPlan]


class JoinIn(Strict):
    """The public join form (§16.4, 9.5): an enquiry, never a member."""

    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    email: OptionalEmail = None
    branch_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    source: Literal[
        "walk_in", "phone", "facebook", "instagram", "tiktok", "referral", "other"
    ] = "other"
    message: str | None = Field(default=None, max_length=500)
