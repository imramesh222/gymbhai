"""Members: the people who train (PLAN.md §5.5, §6)."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin


class Member(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "members"
    __table_args__ = (
        Index("uq_members_gym_code", "gym_id", "member_code", unique=True),
        # Phone is NOT unique: families often share one number (§5.5).
        Index("ix_members_gym_phone", "gym_id", "phone"),
        Index("uq_members_gym_card", "gym_id", "card_token", unique=True),
    )

    home_branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    # "FZ-0042": the gym's prefix and a per-gym counter.
    member_code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(254))
    gender: Mapped[str | None] = mapped_column(String(16))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(String(255))
    emergency_contact: Mapped[str | None] = mapped_column(String(120))
    # A storage key, not a URL: photos are served through signed links (§11).
    photo_key: Mapped[str | None] = mapped_column(String(255))
    joined_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    app_access: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    # QR identity (§4.2). The secret signs the rotating app code; the card
    # token is the static printed card; bumping the version revokes both.
    qr_secret: Mapped[str] = mapped_column(String(64))
    qr_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1")
    )
    card_token: Mapped[str] = mapped_column(String(32))
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
