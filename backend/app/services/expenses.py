"""Expenses: money the gym spent (PLAN.md §18.1).

Never deleted: a mistake is voided with a reason, and every change is logged
with before and after, as payments are. Seeing them, totals included, needs
"See money totals and reports", because salaries are among them.
"""

import datetime as dt
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError, not_found
from app.core.time import today_in_nepal, utcnow
from app.models.expense import Expense
from app.services import activity, live
from app.services import members as members_service

TRACKED = ("branch_id", "category", "amount", "spent_on", "method", "paid_to", "note")
# Always have a value: a null sent for one of these leaves it as it is.
REQUIRED = ("category", "amount", "spent_on", "method")


def snapshot(expense: Expense) -> dict[str, Any]:
    return {name: getattr(expense, name) for name in TRACKED}


def in_branches(stmt: Select, branches: frozenset[uuid.UUID] | None) -> Select:
    """Staff limited to some branches see theirs. The whole gym's expenses
    (no branch) are for those who work at every branch."""
    if branches is None:
        return stmt
    return stmt.where(Expense.branch_id.in_(branches))


def visible(ctx: StaffContext) -> Select:
    return in_branches(
        select(Expense).where(Expense.gym_id == ctx.gym_id), ctx.branch_ids
    )


def load(
    db: Session, ctx: StaffContext, expense_id: uuid.UUID, *, for_update: bool = False
) -> Expense:
    """One of this gym's expenses, at a branch the caller works at, or 404."""
    stmt = visible(ctx).where(Expense.id == expense_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    expense = db.scalar(stmt)
    if expense is None:
        raise not_found("No such expense.")
    return expense


def _check(db: Session, ctx: StaffContext, values: dict[str, Any]) -> None:
    """The branch is this gym's and the caller's; the day has come."""
    if "branch_id" in values:
        if values["branch_id"] is not None:
            members_service._branch(db, ctx, values["branch_id"])
        elif ctx.branch_ids is not None:
            raise AppError(
                403,
                "branch_denied",
                "Choose one of your branches: the whole gym's expenses are for "
                "staff who work at every branch.",
            )
    if values.get("spent_on") is not None and values["spent_on"] > today_in_nepal():
        raise AppError(422, "future_date", "That day hasn't come yet.")
    for name in ("paid_to", "note"):
        if name in values:
            values[name] = (values[name] or "").strip() or None


def _changed(db: Session, expense: Expense, branch_id: uuid.UUID | None) -> None:
    live.publish(db, gym_id=expense.gym_id, kind=live.EXPENSE, branch_id=branch_id)


def create(
    db: Session,
    ctx: StaffContext,
    values: dict[str, Any],
    request: Request | None = None,
) -> Expense:
    values = dict(values)
    values["spent_on"] = values.get("spent_on") or today_in_nepal()
    _check(db, ctx, values)
    expense = Expense(gym_id=ctx.gym_id, created_by=ctx.staff.id, **values)
    db.add(expense)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "expense.created",
        entity="expense",
        entity_id=expense.id,
        changes=activity.diff({}, snapshot(expense)),
        request=request,
    )
    _changed(db, expense, expense.branch_id)
    return expense


def update(
    db: Session,
    ctx: StaffContext,
    expense: Expense,
    changes: dict[str, Any],
    *,
    reason: str | None = None,
    request: Request | None = None,
) -> Expense:
    if expense.voided_at is not None:
        raise AppError(409, "expense_voided", "This expense has been voided.")
    changes = {
        name: value
        for name, value in changes.items()
        if value is not None or name not in REQUIRED
    }
    _check(db, ctx, changes)
    before = snapshot(expense)
    for name, value in changes.items():
        setattr(expense, name, value)
    diff = activity.diff(before, snapshot(expense))
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "expense.updated",
            entity="expense",
            entity_id=expense.id,
            changes=diff,
            reason=reason,
            request=request,
        )
        _changed(db, expense, expense.branch_id)
        # Moved to another branch: the one it left reloads too.
        if before["branch_id"] != expense.branch_id:
            _changed(db, expense, before["branch_id"])
    return expense


def void(
    db: Session,
    ctx: StaffContext,
    expense: Expense,
    reason: str,
    request: Request | None = None,
) -> Expense:
    if expense.voided_at is not None:
        raise AppError(409, "expense_voided", "This expense has already been voided.")
    expense.voided_at = utcnow()
    expense.voided_by = ctx.staff.id
    expense.void_reason = reason
    activity.staff_action(
        db,
        ctx.staff,
        "expense.voided",
        entity="expense",
        entity_id=expense.id,
        changes={"amount": expense.amount, "category": expense.category},
        reason=reason,
        request=request,
    )
    _changed(db, expense, expense.branch_id)
    return expense


def totals(
    db: Session,
    gym_id: uuid.UUID,
    first: dt.date,
    last: dt.date,
    branches: frozenset[uuid.UUID] | None = None,
    *,
    category: str | None = None,
) -> tuple[int, dict[str, int]]:
    """Spent from `first` to `last` (inclusive), voids left out, and by category."""
    stmt = in_branches(
        select(Expense.category, func.sum(Expense.amount)).where(
            Expense.gym_id == gym_id,
            Expense.voided_at.is_(None),
            Expense.spent_on >= first,
            Expense.spent_on <= last,
        ),
        branches,
    )
    if category:
        stmt = stmt.where(Expense.category == category)
    by_category = {
        name: int(amount)
        for name, amount in db.execute(stmt.group_by(Expense.category)).all()
    }
    return sum(by_category.values()), by_category
