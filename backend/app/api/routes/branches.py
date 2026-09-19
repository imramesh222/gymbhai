"""Branches. Every staff member sees the branches they work in; adding and
editing them is part of Gym settings."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext, for_gym, get_in_gym, in_branches
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.gym import Branch
from app.schemas.gym import BranchCreate, BranchRead, BranchUpdate
from app.services import activity

FIELDS = ("name", "address", "phone", "is_active")
NAME_TAKEN = AppError(
    409, "branch_name_taken", "There is already a branch with that name."
)

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=list[BranchRead])
def list_branches(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(require())
) -> list[Branch]:
    stmt = in_branches(for_gym(select(Branch), Branch, ctx), Branch.id, ctx)
    return list(db.scalars(stmt.order_by(Branch.created_at, Branch.name)))


@router.get("/{branch_id}", response_model=BranchRead)
def get_branch(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require()),
) -> Branch:
    return get_in_gym(
        db, Branch, branch_id, ctx, branch_column=Branch.id, message="No such branch."
    )


@router.post("", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(
    payload: BranchCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_GYM)),
) -> Branch:
    branch = Branch(gym_id=ctx.gym_id, **payload.model_dump())
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise NAME_TAKEN from exc
    activity.staff_action(
        db,
        ctx.staff,
        "branch.created",
        entity="branch",
        entity_id=branch.id,
        changes=payload.model_dump(),
        request=request,
    )
    db.commit()
    return branch


@router.patch("/{branch_id}", response_model=BranchRead)
def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.SETUP_GYM)),
) -> Branch:
    branch = get_in_gym(
        db, Branch, branch_id, ctx, branch_column=Branch.id, message="No such branch."
    )
    before = {name: getattr(branch, name) for name in FIELDS}
    for name, value in payload.model_dump(exclude_unset=True).items():
        if value is None and name in ("name", "is_active"):
            continue
        setattr(branch, name, value)
    if not branch.is_active and before["is_active"]:
        remaining = db.scalar(
            select(Branch.id).where(
                Branch.gym_id == ctx.gym_id, Branch.is_active, Branch.id != branch.id
            )
        )
        if remaining is None:
            raise AppError(409, "last_branch", "A gym needs at least one open branch.")
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise NAME_TAKEN from exc
    diff = activity.diff(before, {name: getattr(branch, name) for name in FIELDS})
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "branch.updated",
            entity="branch",
            entity_id=branch.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return branch
