"""Members' app payments waiting for staff (PLAN.md §5.4, §7 Payment requests)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.routes.member_app import request_read
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.member import Member
from app.models.member_app import REQUEST_PENDING, PaymentRequest
from app.models.plan import Plan
from app.models.staff import StaffUser
from app.schemas.member_app import ApproveIn, PaymentRequestRead, RejectIn
from app.services import memberships as ms
from app.services import payment_requests as service

router = APIRouter(prefix="/payment-requests", tags=["payment requests"])

APPROVE = require(Permission.PAYMENTS_APPROVE_APP)


def _read(db: Session, row: PaymentRequest) -> PaymentRequestRead:
    read = request_read(db, row)
    member = db.get(Member, row.member_id)
    if member is not None:
        read.member_name = member.name
        read.member_code = member.member_code
        plan = db.get(Plan, row.plan_id)
        if plan is not None and plan.price is not None:
            first = ms.is_first_membership(db, member)
            read.expected_total = plan.price + (plan.admission_fee if first else 0)
    if row.reviewed_by:
        reviewer = db.get(StaffUser, row.reviewed_by)
        read.reviewed_by_name = reviewer.name if reviewer else None
    return read


def _load(db: Session, ctx: StaffContext, request_id: uuid.UUID) -> PaymentRequest:
    return get_in_gym(db, PaymentRequest, request_id, ctx, message="No such request.")


@router.get("", response_model=list[PaymentRequestRead])
def list_requests(
    request_status: Annotated[
        str, Query(alias="status", pattern="^(pending|approved|rejected|withdrawn)$")
    ] = REQUEST_PENDING,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(APPROVE),
) -> list[PaymentRequestRead]:
    stmt = for_gym(select(PaymentRequest), PaymentRequest, ctx).where(
        PaymentRequest.status == request_status
    )
    rows = db.scalars(stmt.order_by(PaymentRequest.created_at).limit(200))
    return [_read(db, r) for r in rows]


@router.get("/count")
def pending_count(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(APPROVE)
) -> dict[str, int]:
    """The red count on Payment requests (§5.4)."""
    count = db.scalar(
        select(func.count())
        .select_from(PaymentRequest)
        .where(
            PaymentRequest.gym_id == ctx.gym_id,
            PaymentRequest.status == REQUEST_PENDING,
        )
    )
    return {"pending": count or 0}


@router.post("/{request_id}/approve", response_model=PaymentRequestRead)
def approve(
    request_id: uuid.UUID,
    payload: ApproveIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(APPROVE),
) -> PaymentRequestRead:
    row = _load(db, ctx, request_id)
    service.approve(
        db,
        ctx,
        row,
        price=payload.price,
        discount=payload.discount,
        accept_part_payment=payload.accept_part_payment,
        request=request,
    )
    db.commit()
    return _read(db, row)


@router.post("/{request_id}/reject", response_model=PaymentRequestRead)
def reject(
    request_id: uuid.UUID,
    payload: RejectIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(APPROVE),
) -> PaymentRequestRead:
    row = _load(db, ctx, request_id)
    service.reject(db, ctx, row, payload.reason, request=request)
    db.commit()
    return _read(db, row)
