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
    return next_values(db, gym_id, name, 1)[0]


def next_values(db: Session, gym_id: uuid.UUID, name: str, count: int) -> range:
    """`count` consecutive numbers in one statement (an imported register)."""
    last = db.execute(
        text(
            """
            INSERT INTO gym_counters (id, gym_id, name, value)
            VALUES (:id, :gym_id, :name, :count)
            ON CONFLICT (gym_id, name)
            DO UPDATE SET value = gym_counters.value + :count, updated_at = now()
            RETURNING value
            """
        ),
        {"id": uuid.uuid4(), "gym_id": gym_id, "name": name, "count": count},
    ).scalar_one()
    return range(last - count + 1, last + 1)


def peek(db: Session, gym_id: uuid.UUID, name: str) -> int:
    """The last number issued, 0 if none. For display only; never to reserve."""
    value = db.execute(
        text("SELECT value FROM gym_counters WHERE gym_id = :gym_id AND name = :name"),
        {"gym_id": gym_id, "name": name},
    ).scalar()
    return value or 0
