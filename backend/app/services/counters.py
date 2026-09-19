"""Per-gym sequence numbers: member codes, receipt numbers (PLAN.md §6).

One atomic upsert per number. Two desks saving at the same moment get
consecutive numbers, never the same one: the second waits on the first's row
lock until it commits.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

MEMBER_CODE = "member_code"
RECEIPT_NO = "receipt_no"


def next_value(db: Session, gym_id: uuid.UUID, name: str) -> int:
    return db.execute(
        text(
            """
            INSERT INTO gym_counters (id, gym_id, name, value)
            VALUES (:id, :gym_id, :name, 1)
            ON CONFLICT (gym_id, name)
            DO UPDATE SET value = gym_counters.value + 1, updated_at = now()
            RETURNING value
            """
        ),
        {"id": uuid.uuid4(), "gym_id": gym_id, "name": name},
    ).scalar_one()


def peek(db: Session, gym_id: uuid.UUID, name: str) -> int:
    """The last number issued, 0 if none. For display only; never to reserve."""
    value = db.execute(
        text("SELECT value FROM gym_counters WHERE gym_id = :gym_id AND name = :name"),
        {"gym_id": gym_id, "name": name},
    ).scalar()
    return value or 0
