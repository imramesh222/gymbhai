"""The worker's queue: a Postgres table claimed with FOR UPDATE SKIP LOCKED."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # The claim query only ever looks at unfinished jobs.
        Index("ix_jobs_due", "run_at", postgresql_where=text("done_at IS NULL")),
    )

    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the job succeeded, or gave up. `error` tells the two apart.
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
