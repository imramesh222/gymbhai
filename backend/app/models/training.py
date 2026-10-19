"""Personal training (PLAN.md §18.3): the gym's PT plans, what was sold, and
the sessions trained.

Like memberships, a package's status is never stored: it is computed from its
dates, cancelled_at and the sessions recorded (app/services/training.py). The
plan's name, kind, sessions and price are copied at sale, so changing a plan
later changes nothing sold. Sessions are never deleted, only voided with a
reason.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# Training for the plan's length, or a pack of sessions to use within it.
KIND_MONTHLY = "monthly"
KIND_SESSIONS = "sessions"
KINDS = (KIND_MONTHLY, KIND_SESSIONS)


class PtPlan(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "pt_plans"
    __table_args__ = (
        CheckConstraint("kind IN ('monthly', 'sessions')", name="kind"),
        # A pack says how many sessions; a monthly plan doesn't count them.
        CheckConstraint("(kind = 'sessions') = (sessions IS NOT NULL)", name="pack"),
        CheckConstraint("sessions IS NULL OR sessions > 0", name="sessions"),
        CheckConstraint(
            "(duration_months IS NULL) <> (duration_days IS NULL)",
            name="one_duration",
        ),
        CheckConstraint(
            "duration_months IS NULL OR duration_months > 0", name="months"
        ),
        CheckConstraint("duration_days IS NULL OR duration_days > 0", name="days"),
        CheckConstraint("price >= 0", name="price"),
    )

    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    sessions: Mapped[int | None] = mapped_column(Integer)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    # Paisa.
    price: Mapped[int] = mapped_column(Integer)
    # False: hidden, no longer sold. Never deleted: packages point at it.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )


class PtPackage(IdMixin, TimestampMixin, GymOwned, Base):
    """Personal training sold to one member, with one trainer."""

    __tablename__ = "pt_packages"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates"),
        CheckConstraint(
            "price >= 0 AND discount >= 0 AND discount <= price", name="money"
        ),
        CheckConstraint("kind IN ('monthly', 'sessions')", name="kind"),
        CheckConstraint("(kind = 'sessions') = (sessions IS NOT NULL)", name="pack"),
        CheckConstraint("sessions IS NULL OR sessions > 0", name="sessions"),
        Index("ix_pt_packages_trainer_end", "trainer_id", "end_date"),
        Index("ix_pt_packages_gym_end", "gym_id", "end_date"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pt_plans.id")
    )
    # Copied at sale (see the module's docstring).
    plan_name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    sessions: Mapped[int | None] = mapped_column(Integer)
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    # Where they train: the member's home branch unless chosen. Staff limited
    # to some branches see the packages there, and their payments.
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    # Inclusive: the last day they may train.
    end_date: Mapped[date] = mapped_column(Date)
    # Paisa.
    price: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


class PtSession(IdMixin, TimestampMixin, GymOwned, Base):
    """One session trained. For a monthly package, the trainer's attendance."""

    __tablename__ = "pt_sessions"

    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pt_packages.id"), index=True
    )
    # A Nepal day.
    trained_on: Mapped[date] = mapped_column(Date)
    # The package's trainer that day: it can change during a package.
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)
