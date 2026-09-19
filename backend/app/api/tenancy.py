"""Keeping each gym's data separate (PLAN.md §3, "Tenancy").

The gym always comes from the signed-in user, never from the request. Routes
get a StaffContext from `require(...)` (app/api/deps.py) and read gym-owned
rows only through the helpers below:

    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW))
    member = get_in_gym(db, Member, member_id, ctx)          # 404 if not ours
    rows = db.scalars(for_gym(select(Member), Member, ctx))  # only ours

Another gym's record is reported as not found, never forbidden: a 403 would
confirm that the id exists.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import not_found
from app.core.permissions import Permission
from app.models.staff import StaffUser


@dataclass(frozen=True)
class StaffContext:
    """Who is asking, for which gym, and what they may do. Built per request."""

    staff: StaffUser
    gym_id: uuid.UUID
    permissions: frozenset[Permission]
    # None means every branch.
    branch_ids: frozenset[uuid.UUID] | None

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def can_access_branch(self, branch_id: uuid.UUID | None) -> bool:
        return self.branch_ids is None or branch_id in self.branch_ids


def for_gym(stmt: Select[Any], model: Any, ctx: StaffContext) -> Select[Any]:
    """Limit a query on a gym-owned model to the caller's gym."""
    return stmt.where(model.gym_id == ctx.gym_id)


def in_branches(
    stmt: Select[Any], column: InstrumentedAttribute[Any], ctx: StaffContext
) -> Select[Any]:
    """Further limit it to the branches the caller may see."""
    if ctx.branch_ids is None:
        return stmt
    return stmt.where(column.in_(ctx.branch_ids))


def get_in_gym[T](
    db: Session,
    model: type[T],
    record_id: uuid.UUID,
    ctx: StaffContext,
    *,
    branch_column: InstrumentedAttribute[Any] | None = None,
    message: str = "Not found.",
) -> T:
    """One row of the caller's gym (and branches, if given), or 404."""
    stmt = for_gym(select(model), model, ctx).where(model.id == record_id)  # type: ignore[attr-defined]
    if branch_column is not None:
        stmt = in_branches(stmt, branch_column, ctx)
    row = db.scalars(stmt).first()
    if row is None:
        raise not_found(message)
    return row
