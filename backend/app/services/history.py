"""The History tab (PLAN.md §5.6): who changed what, when, before and after."""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.activity import ACTOR_STAFF, ActivityLog
from app.models.staff import StaffUser
from app.schemas.members import HistoryEntry


def history_for(
    db: Session, gym_id: uuid.UUID, conditions: list[Any], limit: int = 200
) -> list[HistoryEntry]:
    rows = list(
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.gym_id == gym_id, or_(*conditions))
            .order_by(ActivityLog.at.desc(), ActivityLog.created_at.desc())
            .limit(limit)
        )
    )
    staff_ids = {r.actor_id for r in rows if r.actor_type == ACTOR_STAFF and r.actor_id}
    names = (
        dict(
            db.execute(
                select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(staff_ids))
            ).all()
        )
        if staff_ids
        else {}
    )
    return [
        HistoryEntry(
            id=r.id,
            at=r.at,
            action=r.action,
            actor_name=names.get(r.actor_id) if r.actor_id else None,
            changes=r.changes,
            reason=r.reason,
        )
        for r in rows
    ]
