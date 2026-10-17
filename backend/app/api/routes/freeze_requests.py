"""Freeze requests from the member app, for staff to answer (PLAN.md §16.3, 8.6)."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import staff_names
from app.api.tenancy import StaffContext, get_in_gym
from app.core.errors import not_found
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.member import Member
from app.models.member_app import REQUEST_PENDING, FreezeRequest
from app.models.membership import Membership
from app.schemas.member_app import FreezeRequestRead, RejectIn
from app.services import freeze_requests as service

router = APIRouter(prefix="/freeze-requests", tags=["freeze requests"])

FREEZE = require(Permission.MEMBERSHIPS_FREEZE)


def reads(db: Session, rows: Sequence[FreezeRequest]) -> list[FreezeRequestRead]:
    """Who, which membership, who answered: one query each for the whole list."""
    members = {
        m.id: m
        for m in db.execute(
            select(Member.id, Member.name, Member.member_code).where(
                Member.id.in_({r.member_id for r in rows})
            )
        )
    }
    memberships = {
        m.id: m
        for m in db.execute(
            select(Membership.id, Membership.plan_name, Membership.end_date).where(
                Membership.id.in_({r.membership_id for r in rows})
            )
        )
    }
    reviewers = staff_names(db, [r.reviewed_by for r in rows])
    out = []
    for row in rows:
        read = FreezeRequestRead.model_validate(row)
        if member := members.get(row.member_id):
            read.member_name, read.member_code = member.name, member.member_code
        if membership := memberships.get(row.membership_id):
            read.plan_name, read.ends_on = membership.plan_name, membership.end_date
        if row.reviewed_by:
            read.reviewed_by_name = reviewers.get(row.reviewed_by)
        out.append(read)
    return out


def _visible(ctx: StaffContext):
    """This gym's requests, from members at branches the staff member works at."""
    stmt = (
        select(FreezeRequest)
        .join(Member, Member.id == FreezeRequest.member_id)
        .where(FreezeRequest.gym_id == ctx.gym_id)
    )
    if ctx.branch_ids is not None:
        stmt = stmt.where(Member.home_branch_id.in_(ctx.branch_ids))
    return stmt


def _load(db: Session, ctx: StaffContext, request_id: uuid.UUID) -> FreezeRequest:
    row = get_in_gym(
        db, FreezeRequest, request_id, ctx, message="No such request.", for_update=True
    )
    member = db.get(Member, row.member_id)
    if member is None or not ctx.can_access_branch(member.home_branch_id):
        raise not_found("No such request.")
    return row


@router.get("", response_model=list[FreezeRequestRead])
def list_requests(
    request_status: Annotated[
        str, Query(alias="status", pattern="^(pending|approved|rejected|withdrawn)$")
    ] = REQUEST_PENDING,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(FREEZE),
) -> list[FreezeRequestRead]:
    rows = db.scalars(
        _visible(ctx)
        .where(FreezeRequest.status == request_status)
        .order_by(FreezeRequest.created_at)
        .limit(200)
    ).all()
    return reads(db, rows)


@router.get("/count")
def pending_count(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(FREEZE)
) -> dict[str, int]:
    """The count beside Freeze requests in the menu."""
    stmt = _visible(ctx).where(FreezeRequest.status == REQUEST_PENDING)
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"pending": count or 0}


@router.post("/{freeze_request_id}/approve", response_model=FreezeRequestRead)
def approve(
    freeze_request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(FREEZE),
) -> FreezeRequestRead:
    row = service.approve(db, ctx, _load(db, ctx, freeze_request_id), request=request)
    db.commit()
    return reads(db, [row])[0]


@router.post("/{freeze_request_id}/reject", response_model=FreezeRequestRead)
def reject(
    freeze_request_id: uuid.UUID,
    payload: RejectIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(FREEZE),
) -> FreezeRequestRead:
    row = service.reject(
        db, ctx, _load(db, ctx, freeze_request_id), payload.reason, request=request
    )
    db.commit()
    return reads(db, [row])[0]
