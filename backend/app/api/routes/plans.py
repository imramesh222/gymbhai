"""The gym's plans (PLAN.md §5.1). Hidden, never deleted: memberships point at them."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.gym import Branch
from app.models.plan import Plan, PlanBranch
from app.schemas.plans import PlanCreate, PlanRead, PlanUpdate
from app.services import activity

router = APIRouter(prefix="/plans", tags=["plans"])

FIELDS = (
    "name",
    "duration_months",
    "duration_days",
    "price",
    "admission_fee",
    "all_branches",
    "is_active",
    "sort_order",
)


def _branch_ids(db: Session, plan_id: uuid.UUID) -> list[uuid.UUID]:
    return sorted(
        db.scalars(select(PlanBranch.branch_id).where(PlanBranch.plan_id == plan_id))
    )


def _read(db: Session, plan: Plan) -> PlanRead:
    read = PlanRead.model_validate(plan)
    read.branch_ids = [] if plan.all_branches else _branch_ids(db, plan.id)
    return read


def _set_branches(
    db: Session, ctx: StaffContext, plan: Plan, branch_ids: list[uuid.UUID]
) -> None:
    wanted = set(branch_ids)
    found = set(
        db.scalars(
            select(Branch.id).where(Branch.gym_id == ctx.gym_id, Branch.id.in_(wanted))
        )
    )
    if found != wanted:
        raise AppError(422, "bad_branch", "That branch does not exist.")
    db.execute(delete(PlanBranch).where(PlanBranch.plan_id == plan.id))
    for branch_id in sorted(wanted):
        db.add(PlanBranch(plan_id=plan.id, branch_id=branch_id))


@router.get("", response_model=list[PlanRead])
def list_plans(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require()),
) -> list[PlanRead]:
    stmt = for_gym(select(Plan), Plan, ctx)
    if not include_hidden:
        stmt = stmt.where(Plan.is_active)
    rows = db.scalars(stmt.order_by(Plan.sort_order, Plan.created_at))
    return [_read(db, p) for p in rows]


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_PLANS)),
) -> PlanRead:
    plan = Plan(gym_id=ctx.gym_id, **payload.model_dump(exclude={"branch_ids"}))
    db.add(plan)
    db.flush()
    if not plan.all_branches:
        _set_branches(db, ctx, plan, payload.branch_ids)
    activity.staff_action(
        db,
        ctx.staff,
        "plan.created",
        entity="plan",
        entity_id=plan.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return _read(db, plan)


@router.patch("/{plan_id}", response_model=PlanRead)
def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_PLANS)),
) -> PlanRead:
    plan = get_in_gym(db, Plan, plan_id, ctx, message="No such plan.")
    changes = payload.model_dump(exclude_unset=True)
    before = {name: getattr(plan, name) for name in FIELDS}
    before["branch_ids"] = _branch_ids(db, plan.id)

    # Switching between months and days replaces the other.
    if changes.get("duration_months") is not None:
        changes["duration_days"] = None
    elif changes.get("duration_days") is not None:
        changes["duration_months"] = None
    for name in FIELDS:
        if name in changes:
            if changes[name] is None and name not in (
                "price",
                "duration_months",
                "duration_days",
            ):
                continue
            setattr(plan, name, changes[name])
    if plan.duration_months is None and plan.duration_days is None:
        raise AppError(422, "needs_duration", "Give a duration in months or in days.")
    if changes.get("branch_ids") is not None:
        _set_branches(db, ctx, plan, changes["branch_ids"])
    db.flush()
    if not plan.all_branches and not _branch_ids(db, plan.id):
        raise AppError(422, "needs_branch", "Choose at least one branch.")

    after = {name: getattr(plan, name) for name in FIELDS}
    after["branch_ids"] = _branch_ids(db, plan.id)
    diff = activity.diff(before, after)
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "plan.updated",
            entity="plan",
            entity_id=plan.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return _read(db, plan)
