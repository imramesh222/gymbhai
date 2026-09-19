"""Writing the activity log (PLAN.md §5.6, §11).

Entries are added to the caller's session and committed with the change they
describe, so a change is never saved without its log entry, or the reverse.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import Request
from pydantic_core import to_jsonable_python
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.activity import ACTOR_STAFF, ActivityLog
from app.models.staff import StaffUser


def client_ip(request: Request | None) -> str | None:
    """The caller's address, not one of our proxies'.

    X-Forwarded-For is a list the client starts and every proxy appends to, so
    the entries a caller can forge are on the left. Counting in from the right
    by the number of proxies we run lands on the one they cannot choose.
    """
    if request is None:
        return None
    hops = settings.trusted_proxy_count
    forwarded = request.headers.get("X-Forwarded-For")
    if hops > 0 and forwarded:
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(chain) >= hops:
            return chain[-hops][:64]
    return request.client.host[:64] if request.client else None


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """{"field": {"before": x, "after": y}} for each field whose value changed."""
    changes = {}
    for key in sorted(set(before) | set(after)):
        old = to_jsonable_python(before.get(key))
        new = to_jsonable_python(after.get(key))
        if old != new:
            changes[key] = {"before": old, "after": new}
    return changes


def record(
    db: Session,
    *,
    gym_id: uuid.UUID | None,
    actor_type: str,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    changes: Mapping[str, Any] | None = None,
    reason: str | None = None,
    request: Request | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        gym_id=gym_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        changes=to_jsonable_python(changes) if changes is not None else None,
        reason=reason,
        ip=client_ip(request),
    )
    db.add(entry)
    return entry


def staff_action(
    db: Session, staff: StaffUser, action: str, **kwargs: Any
) -> ActivityLog:
    return record(
        db,
        gym_id=kwargs.pop("gym_id", staff.gym_id),
        actor_type=ACTOR_STAFF,
        actor_id=staff.id,
        action=action,
        **kwargs,
    )
