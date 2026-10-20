"""Memberships (PLAN.md §5, §6).

Status is never stored: it is computed from the dates, the freezes and
cancelled_at (app/services/memberships.py). A renewal is a new row; nothing is
overwritten, and every edit is in activity_log.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

SOURCE_DESK = "desk"
SOURCE_APP = "app_request"
SOURCE_IMPORT = "import"


class Membership(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates"),
        CheckConstraint(
            "price >= 0 AND discount >= 0 AND admission_fee >= 0", name="money"
        ),
        Index("ix_memberships_member_end", "member_id", "end_date"),
        Index("ix_memberships_gym_end", "gym_id", "end_date"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id")
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id")
    )
    # Copied at sale, so renaming a plan never rewrites what a member bought.
    plan_name: Mapped[str] = mapped_column(String(80))
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    # Inclusive: the last day the member may train.
    end_date: Mapped[date] = mapped_column(Date)
    # Paisa, copied from the plan at sale (§5.1).
    price: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    admission_fee: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    source: Mapped[str] = mapped_column(String(16), default=SOURCE_DESK)
    # Copied from the plan at sale (§16.4, 9.3, 9.4): changing the plan later
    # never changes what a member bought.
    visit_limit: Mapped[int | None] = mapped_column(Integer)
    access_hours: Mapped[list | None] = mapped_column(JSONB)
    # Sold with others on a family or couple plan (§19.1). The payer's
    # membership carries the price and every payment; the others carry 0.
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("membership_groups.id"), index=True
    )
    # Copied from the plan at sale (§19.4): the classes it lets them book.
    classes: Mapped[str] = mapped_column(
        String(8), default="all", server_default=text("'all'")
    )
    class_type_ids: Mapped[list | None] = mapped_column(JSONB)


class MembershipGroup(IdMixin, TimestampMixin, GymOwned, Base):
    """One sale for several people: a couple, a parent and children (§19.1).

    Each person has an ordinary membership of their own (dates, status,
    freezes, visits); this ties them together and says who pays.
    """

    __tablename__ = "membership_groups"
    __table_args__ = (CheckConstraint("seats BETWEEN 2 AND 6", name="seats"),)

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id")
    )
    payer_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    # Copied from the plan at sale, like its price.
    seats: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


class MembershipFreeze(IdMixin, TimestampMixin, GymOwned, Base):
    """A pause. Freezing moves the membership's end_date by the frozen days."""

    __tablename__ = "membership_freezes"
    __table_args__ = (CheckConstraint("to_date >= from_date", name="dates"),)

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    from_date: Mapped[date] = mapped_column(Date)
    # Inclusive.
    to_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
