"""A gym's own plans (PLAN.md §5.1): what members buy."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# Seeded on sign-up with prices left blank for the owner to fill in.
DEFAULT_PLANS = (("1 month", 1), ("3 months", 3), ("6 months", 6), ("1 year", 12))


class Plan(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "(duration_months IS NULL) <> (duration_days IS NULL)",
            name="one_duration",
        ),
        CheckConstraint(
            "duration_months IS NULL OR duration_months > 0", name="months"
        ),
        CheckConstraint("duration_days IS NULL OR duration_days > 0", name="days"),
        CheckConstraint("price IS NULL OR price >= 0", name="price"),
        CheckConstraint("admission_fee >= 0", name="admission_fee"),
        CheckConstraint("visit_limit IS NULL OR visit_limit > 0", name="visit_limit"),
        CheckConstraint("seats BETWEEN 1 AND 6", name="seats"),
        # Whose visits would they be? (§19.1)
        CheckConstraint("seats = 1 OR visit_limit IS NULL", name="seats_no_visits"),
    )

    name: Mapped[str] = mapped_column(String(80))
    duration_months: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    # Paisa. Null until the owner sets it; such a plan cannot be sold.
    price: Mapped[int | None] = mapped_column(Integer)
    admission_fee: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    # False means only the branches in plan_branches.
    all_branches: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    # A visit pack: this many visits within the dates; null is unlimited
    # (§16.4, 9.3). Copied onto each membership sold.
    visit_limit: Mapped[int | None] = mapped_column(Integer)
    # Off-peak: when the door lets them in, as [{"days": [0..6, Monday is 0],
    # "from": "06:00", "to": "10:00"}] in Nepal time; null is any time (9.4).
    access_hours: Mapped[list | None] = mapped_column(JSONB)
    # People one sale covers: 2 for a couple, up to 6 for a family (§19.1).
    seats: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    # The classes it lets members book (§19.4): none, all, or the chosen
    # types. Copied onto each membership sold.
    classes: Mapped[str] = mapped_column(
        String(8), default="all", server_default=text("'all'")
    )
    class_type_ids: Mapped[list | None] = mapped_column(JSONB)


class PlanBranch(IdMixin, TimestampMixin, Base):
    __tablename__ = "plan_branches"
    __table_args__ = (UniqueConstraint("plan_id", "branch_id"),)

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), index=True
    )
