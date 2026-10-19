"""Expenses: money the gym spent (PLAN.md §18.1).

Never deleted, only voided with a reason; every edit is logged.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import require
from app.api.presenters import staff_names
from app.api.tenancy import StaffContext
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.expense import Expense
from app.models.gym import Gym
from app.schemas.expenses import (
    Category,
    ExpenseIn,
    ExpenseList,
    ExpenseRead,
    ExpenseUpdate,
)
from app.schemas.money import VoidIn
from app.services import expenses as service
from app.services import reports

router = APIRouter(prefix="/expenses", tags=["expenses"])

# A month of one gym's spending is far fewer; the totals count every row anyway.
LISTED = 1000


def _read(expense: Expense, names: dict[uuid.UUID, str]) -> ExpenseRead:
    read = ExpenseRead.model_validate(expense)
    read.created_by_name = names.get(expense.created_by) if expense.created_by else None
    return read


def reads(db: Session, rows: Sequence[Expense]) -> list[ExpenseRead]:
    names = staff_names(db, [row.created_by for row in rows])
    return [_read(row, names) for row in rows]


@router.get("", response_model=ExpenseList)
def list_expenses(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    category: Category | None = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
) -> ExpenseList:
    """A month of the gym's own calendar, newest first, with what it adds up to."""
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    month = month or reports.current_month(calendar)
    first, last = reports.month_range(month, calendar)
    stmt = service.visible(ctx).where(
        Expense.spent_on >= first, Expense.spent_on <= last
    )
    if category:
        stmt = stmt.where(Expense.category == category)
    rows = db.scalars(
        stmt.order_by(Expense.spent_on.desc(), Expense.created_at.desc()).limit(LISTED)
    ).all()
    spent, by_category = service.totals(
        db, ctx.gym_id, first, last, ctx.branch_ids, category=category
    )
    return ExpenseList(
        month=month,
        calendar=calendar,
        first_day=first,
        last_day=last,
        items=reads(db, rows),
        sum_amount=spent,
        by_category=by_category,
    )


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def record_expense(
    payload: ExpenseIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.EXPENSES_RECORD)),
) -> ExpenseRead:
    """Rent, a salary, a bill: recorded once, however often Save is tapped."""
    idem = idempotency.begin(db, ctx, request, payload)
    expense = service.create(db, ctx, payload.model_dump(), request)
    answer = _read(expense, {ctx.staff.id: ctx.staff.name})
    idem.finish(answer)
    db.commit()
    return answer


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.EXPENSES_EDIT)),
) -> ExpenseRead:
    expense = service.load(db, ctx, expense_id, for_update=True)
    service.update(
        db,
        ctx,
        expense,
        payload.model_dump(exclude_unset=True, exclude={"reason"}),
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return reads(db, [expense])[0]


@router.post("/{expense_id}/void", response_model=ExpenseRead)
def void_expense(
    expense_id: uuid.UUID,
    payload: VoidIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.EXPENSES_EDIT)),
) -> ExpenseRead:
    expense = service.load(db, ctx, expense_id, for_update=True)
    service.void(db, ctx, expense, payload.reason, request)
    db.commit()
    return reads(db, [expense])[0]
