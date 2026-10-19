"""Money the gym spent: rent, salaries, bills (PLAN.md §18.1).

Recorded so the owner sees profit, not only income. Like payments, amounts
are integer paisa and nothing is deleted: a mistake is voided with a reason.
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# Fixed, so they translate and add up the same way in every gym. A trainer's
# salary is "salaries", with their name in paid_to.
CATEGORIES = (
    "rent",
    "salaries",
    "electricity",
    "water",
    "internet",
    "equipment",
    "repairs",
    "cleaning",
    "marketing",
    "fees",
    "other",
)


class Expense(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        Index("ix_expenses_gym_spent_on", "gym_id", "spent_on"),
    )

    # None: the whole gym rather than one branch.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id")
    )
    category: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    # A Nepal day: what the money was spent on, not when it was typed in.
    spent_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(16))
    # Who got the money: the landlord, a trainer, the electricity office.
    paid_to: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)
