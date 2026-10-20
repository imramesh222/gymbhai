"""Progress (PLAN.md §19.5): weight, body fat and measurements over time, and
photos only the member sees unless they share them with their trainer.

Stored as whole numbers, as money is stored in paisa: grams, tenths of a
percent, millimetres.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

POSES = ("front", "side", "back")


class ProgressEntry(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "progress_entries"
    __table_args__ = (
        Index("ix_progress_entries_member_on", "member_id", "measured_on"),
        CheckConstraint(
            "weight_g IS NULL OR weight_g BETWEEN 20000 AND 300000", name="weight"
        ),
        CheckConstraint(
            "body_fat IS NULL OR body_fat BETWEEN 10 AND 700", name="body_fat"
        ),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE")
    )
    measured_on: Mapped[date] = mapped_column(Date)
    weight_g: Mapped[int | None] = mapped_column(Integer)
    # Tenths of a percent: 23.5% is 235.
    body_fat: Mapped[int | None] = mapped_column(Integer)
    chest_mm: Mapped[int | None] = mapped_column(Integer)
    waist_mm: Mapped[int | None] = mapped_column(Integer)
    hips_mm: Mapped[int | None] = mapped_column(Integer)
    arm_mm: Mapped[int | None] = mapped_column(Integer)
    thigh_mm: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    # Staff who recorded it; null when the member did, in their app.
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )


class ProgressPhoto(IdMixin, TimestampMixin, GymOwned, Base):
    """Private: only the member sees it, unless `shared` with the trainers of
    their personal training. Never in exports or the activity log."""

    __tablename__ = "progress_photos"
    __table_args__ = (
        CheckConstraint("pose IN ('front', 'side', 'back')", name="pose"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    taken_on: Mapped[date] = mapped_column(Date)
    pose: Mapped[str] = mapped_column(String(8))
    photo_key: Mapped[str] = mapped_column(String(255))
    shared: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
