"""Enquiries: people who might join (PLAN.md §16.4, 9.1)."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# Where they heard of the gym.
SOURCES = ("walk_in", "phone", "facebook", "instagram", "tiktok", "referral", "other")

# new → contacted → trial → joined, or lost at any point.
LEAD_NEW = "new"
LEAD_CONTACTED = "contacted"
LEAD_TRIAL = "trial"
LEAD_JOINED = "joined"
LEAD_LOST = "lost"
STATUSES = (LEAD_NEW, LEAD_CONTACTED, LEAD_TRIAL, LEAD_JOINED, LEAD_LOST)
# Still worth a call.
OPEN = (LEAD_NEW, LEAD_CONTACTED, LEAD_TRIAL)


class Lead(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_gym_status", "gym_id", "status"),
        Index("ix_leads_gym_phone", "gym_id", "phone"),
        Index("ix_leads_gym_follow_up", "gym_id", "follow_up_on"),
        Index("ix_leads_from_ip_created", "from_ip", "created_at"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id")
    )
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(254))
    source: Mapped[str] = mapped_column(String(16))
    # The plan they asked about.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default=LEAD_NEW)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    lost_reason: Mapped[str | None] = mapped_column(String(200))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    # Their trial visit (9.2): not a check-in, as they aren't a member yet.
    trial_on: Mapped[date | None] = mapped_column(Date)
    # A member who sent them (9.6).
    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="SET NULL")
    )
    # Once they join: the member they became.
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    # Sent from the public join form (9.5): where from, for its rate limit.
    # Cleared after a day by the cleanup job.
    from_ip: Mapped[str | None] = mapped_column(String(64))
