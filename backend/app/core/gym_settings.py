"""The per-gym choices stored in `gyms.settings` (PLAN.md §6).

Validated here on the way in and on the way out, so a key typed wrong in a
migration or a script fails loudly instead of quietly meaning "default".
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core import sms_defaults

PlanMonths = Literal["ad", "bs"]
DateDisplay = Literal["ad", "bs", "both"]
DuesRule = Literal["allow", "warn", "refuse"]
Language = Literal["en", "ne"]


class GymSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # How plan months are counted has deliberately no default (PLAN.md §5.1):
    # None until the owner chooses, on Plans or the first sale, and nothing
    # with months can be sold before then. Dates show in both to start.
    plan_months: PlanMonths | None = None
    date_display: DateDisplay = "both"

    # What happens at the door while a member owes money (§5.3).
    dues_rule: DuesRule = "warn"
    # Days after expiry a member is still let in, with a warning (§4.3).
    grace_days: int = Field(default=0, ge=0, le=30)
    # A second scan within this many minutes is "already checked in" (§4.3).
    rescan_minutes: int = Field(default=180, ge=0, le=24 * 60)
    # How long a kiosk keeps letting people in with no internet (§19.2).
    kiosk_offline_days: int = Field(default=3, ge=1, le=7)
    # Classes (§19.4): booking opens this many days ahead, closes this many
    # minutes before the start; cancelling later than this many hours before
    # is a late cancel. A member with `no_show_limit` no-shows in 30 days
    # can't book for `no_show_block_days`; 0 is off.
    class_booking_days: int = Field(default=7, ge=1, le=30)
    class_closes_minutes: int = Field(default=30, ge=0, le=240)
    class_cancel_hours: int = Field(default=2, ge=0, le=48)
    no_show_limit: int = Field(default=0, ge=0, le=10)
    no_show_block_days: int = Field(default=7, ge=1, le=30)
    # An active member with no visit for this many days is "not visiting" on
    # Follow up (§16.3, 8.1).
    not_visiting_days: int = Field(default=14, ge=3, le=90)
    # Member codes are "<prefix>-0042". Changing it only affects new members.
    member_code_prefix: str = Field(default="M", pattern=r"^[A-Z0-9]{1,5}$")
    # SMS wording the gym can edit (§10). Placeholders: app/core/sms_text.py.
    welcome_sms: str = Field(default=sms_defaults.WELCOME["en"], max_length=640)
    membership_sms: str = Field(default=sms_defaults.MEMBERSHIP["en"], max_length=640)
    # "Today: 42 visits, Rs 18,500 collected, 6 expiring this week" to the
    # owner at 8 in the evening (§9). Uses SMS credits, so off by default.
    daily_summary_sms: bool = False
    # Members whose phone takes push get push alone, free (§16.3, 8.3). On:
    # an SMS as well, for gyms whose members don't look at notifications.
    also_sms: bool = False
    # WhatsApp between push and SMS, for members who agreed (§19.3): utility
    # messages only, and each costs the credits set in /admin. Off to start.
    whatsapp: bool = False
    # "Ask to join" behind the gym QR: makes an enquiry (§16.4, 9.5).
    join_form: bool = False
    # "Quiet / Normal / Busy" on the member app's Home (§16.3, 8.5).
    show_busyness: bool = True
    # The gym's language (§16.6): the default for its staff and members, and
    # the language its SMS wording starts in. Each account can choose its own.
    language: Language = "en"
    # Digits on screen when showing Nepali: ०१२ or 012.
    digits: Literal["nepali", "western"] = "western"
    # Every staff account must use two-step sign-in (§16.1). Only the owner
    # changes it (PATCH /gym/security).
    require_two_step: bool = False
    # The setup checklist on Today (§16.2, 7.4): the one step data can't show,
    # and whether the gym put the checklist away.
    poster_printed: bool = False
    setup_dismissed: bool = False
