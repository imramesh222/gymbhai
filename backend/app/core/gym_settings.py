"""The per-gym choices stored in `gyms.settings` (PLAN.md §6).

Validated here on the way in and on the way out, so a key typed wrong in a
migration or a script fails loudly instead of quietly meaning "default".
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlanMonths = Literal["ad", "bs"]
DateDisplay = Literal["ad", "bs", "both"]
DuesRule = Literal["allow", "warn", "refuse"]


class GymSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Chosen at sign-up; there is deliberately no default (PLAN.md §5.1).
    plan_months: PlanMonths
    date_display: DateDisplay

    # What happens at the door while a member owes money (§5.3).
    dues_rule: DuesRule = "warn"
    # Days after expiry a member is still let in, with a warning (§4.3).
    grace_days: int = Field(default=0, ge=0, le=30)
    # A second scan within this many minutes is "already checked in" (§4.3).
    rescan_minutes: int = Field(default=180, ge=0, le=24 * 60)
    # Member codes are "<prefix>-0042". Changing it only affects new members.
    member_code_prefix: str = Field(default="M", pattern=r"^[A-Z0-9]{1,5}$")
    # SMS wording the gym can edit (§10). Placeholders: app/core/sms_text.py.
    welcome_sms: str = Field(
        default="Welcome to {gym}, {name}! Active until {end_date}. "
        "Your app and check-in QR: {link}",
        max_length=640,
    )
    membership_sms: str = Field(
        default="{gym}: your {plan} membership is active until {end_date}. App: {link}",
        max_length=640,
    )
    # "Today: 42 visits, Rs 18,500 collected, 6 expiring this week" to the
    # owner at 8 in the evening (§9). Uses SMS credits, so off by default.
    daily_summary_sms: bool = False
    # Language of the reminder SMS wording (§10). The app itself is English.
    reminder_language: Literal["en", "ne"] = "en"
