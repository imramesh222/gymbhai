"""Members' app payments waiting for staff (PLAN.md §5.4, §7 Payment requests)."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import require
from app.api.presenters import staff_names
from app.api.routes.member_app import requests_read
from app.api.tenancy import StaffContext, for_gym, get_in_gym
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.member import Member
from app.models.member_app import REQUEST_PENDING, PaymentRequest
from app.models.membership import Membership
from app.models.plan import Plan
from app.schemas.member_app import ApproveIn, PaymentRequestRead, RejectIn
from app.services import payment_requests as service

router = APIRouter(prefix="/payment-requests", tags=["payment requests"])

APPROVE = require(Permission.PAYMENTS_APPROVE_APP)


def _reads(db: Session, rows: Sequence[PaymentRequest]) -> list[PaymentRequestRead]:
    """Who, which plan, what it should cost, who reviewed it: one query each,
    however many requests are waiting."""
    reads = requests_read(db, rows)
    member_ids = {r.member_id for r in rows}
    members = {
        m.id: m
        for m in db.execute(
            select(Member.id, Member.name, Member.member_code).where(
                Member.id.in_(member_ids)
            )
        )
    }
    plans = {
        p.id: p
        for p in db.execute(
            select(Plan.id, Plan.price, Plan.admission_fee).where(
                Plan.id.in_({r.plan_id for r in rows})
            )
        )
    }
    # Members with a membership already: no admission fee for them. On a
    # family or couple plan, each newcomer pays one (§19.1).
    people = {uuid.UUID(i) for r in rows for i in r.with_member_ids or []}
    renewing = set(
        db.scalars(
            select(Membership.member_id)
            .where(
                Membership.member_id.in_(member_ids | people),
                Membership.cancelled_at.is_(None),
            )
            .distinct()
        )
    )
    reviewer_names = staff_names(db, [r.reviewed_by for r in rows])
    for row, read in zip(rows, reads, strict=True):
        member = members.get(row.member_id)
        if member is not None:
            read.member_name = member.name
            read.member_code = member.member_code
            plan = plans.get(row.plan_id)
            if plan is not None and plan.price is not None:
                everyone = [row.member_id] + [
                    uuid.UUID(i) for i in row.with_member_ids or []
                ]
                firsts = sum(1 for m in everyone if m not in renewing)
                read.expected_total = plan.price + plan.admission_fee * firsts
        if row.reviewed_by:
            read.reviewed_by_name = reviewer_names.get(row.reviewed_by)
    return reads


def _read(db: Session, row: PaymentRequest) -> PaymentRequestRead:
    return _reads(db, [row])[0]


def _load(db: Session, ctx: StaffContext, request_id: uuid.UUID) -> PaymentRequest:
    """Locked: approving and rejecting first check that it is still pending."""
    return get_in_gym(
        db, PaymentRequest, request_id, ctx, message="No such request.", for_update=True
    )


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
    rows = db.scalars(stmt.order_by(PaymentRequest.created_at).limit(200)).all()
    return _reads(db, rows)


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
    idem = idempotency.begin(db, ctx, request, payload)
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
    answer = _read(db, row)
    idem.finish(answer)
    db.commit()
    return answer


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
