"""What gyms pay us (PLAN.md §5.7).

Prices live in `platform_plans` and are edited from /admin; none are written
into the code. A trial has no plan at all, so it works before any price is set.
"""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

SUBSCRIPTION_TRIAL = "trial"
SUBSCRIPTION_ACTIVE = "active"
SUBSCRIPTION_CANCELLED = "cancelled"


class PlatformPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "platform_plans"

    name: Mapped[str] = mapped_column(String(80))
    # Null means no limit.
    max_active_members: Mapped[int | None] = mapped_column(Integer)
    max_branches: Mapped[int | None] = mapped_column(Integer)
    # Paisa. Null until we decide pricing.
    monthly_price: Mapped[int | None] = mapped_column(Integer)
    included_sms: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )


class GymSubscription(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "gym_subscriptions"

    # Null for the free trial.
    platform_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_plans.id")
    )
    starts_on: Mapped[date] = mapped_column(Date)
    # Inclusive: the last day it covers, like a membership's end date.
    ends_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))


class PlatformSettings(IdMixin, TimestampMixin, Base):
    """Our own numbers that aren't a plan's: one row, edited in /admin.

    Pricing lives in the database, never in the code (CLAUDE.md).
    """

    __tablename__ = "platform_settings"

    # Message credits one WhatsApp message costs a gym (§19.3); an SMS part
    # costs one.
    whatsapp_credits: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1")
    )
    # A gym's own app in the stores (§20.3), in paisa: once to set it up, and
    # each month while it's built and live. Not offered until both are set.
    branded_app_setup_price: Mapped[int | None] = mapped_column(Integer)
    branded_app_monthly_price: Mapped[int | None] = mapped_column(Integer)
