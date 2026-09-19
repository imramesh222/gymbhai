"""Editing memberships (PLAN.md §5.6). Every action here is logged."""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import membership_read_one, payment_read
from app.api.tenancy import StaffContext, get_in_gym
from app.core.errors import not_found
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.activity import ActivityLog
from app.models.gym import Gym
from app.models.membership import Membership, MembershipFreeze
from app.models.payment import Payment
from app.schemas.members import (
    CancelIn,
    ExtendAllIn,
    ExtendAllResult,
    ExtendIn,
    FreezeIn,
    HistoryEntry,
    MembershipRead,
    MembershipUpdate,
    SaleResult,
)
from app.services import memberships as ms
from app.services.history import history_for

router = APIRouter(prefix="/memberships", tags=["memberships"])


def load_membership(
    db: Session, ctx: StaffContext, membership_id: uuid.UUID
) -> Membership:
    return get_in_gym(
        db,
        Membership,
        membership_id,
        ctx,
        branch_column=Membership.branch_id,
        message="No such membership.",
    )


@router.post("/extend-all", response_model=ExtendAllResult)
def extend_all(
    payload: ExtendAllIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_EXTEND_ALL)),
) -> ExtendAllResult:
    """Gym closed for Dashain: every current membership gets N more days."""
    count = ms.extend_all(
        db,
        ctx,
        payload.days,
        payload.reason,
        branch_id=payload.branch_id,
        request=request,
    )
    db.commit()
    return ExtendAllResult(extended=count)


@router.get("/{membership_id}", response_model=MembershipRead)
def get_membership(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> MembershipRead:
    return membership_read_one(db, load_membership(db, ctx, membership_id))


@router.patch("/{membership_id}", response_model=MembershipRead)
def update_membership(
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_EDIT)),
) -> MembershipRead:
    membership = load_membership(db, ctx, membership_id)
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    ms.edit(
        db, ctx, membership, changes, gym.config, reason=payload.reason, request=request
    )
    db.commit()
    return membership_read_one(db, membership)


@router.post("/{membership_id}/extend", response_model=MembershipRead)
def extend(
    membership_id: uuid.UUID,
    payload: ExtendIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_EXTEND)),
) -> MembershipRead:
    membership = load_membership(db, ctx, membership_id)
    ms.extend(db, ctx, membership, payload.days, payload.reason, request=request)
    db.commit()
    return membership_read_one(db, membership)


@router.post("/{membership_id}/freeze", response_model=MembershipRead)
def freeze(
    membership_id: uuid.UUID,
    payload: FreezeIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_FREEZE)),
) -> MembershipRead:
    membership = load_membership(db, ctx, membership_id)
    ms.freeze(
        db,
        ctx,
        membership,
        payload.from_date,
        payload.to_date,
        payload.reason,
        request=request,
    )
    db.commit()
    return membership_read_one(db, membership)


@router.post("/{membership_id}/freezes/{freeze_id}/end", response_model=MembershipRead)
def unfreeze(
    membership_id: uuid.UUID,
    freeze_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_FREEZE)),
) -> MembershipRead:
    membership = load_membership(db, ctx, membership_id)
    row = db.scalar(
        select(MembershipFreeze).where(
            MembershipFreeze.id == freeze_id,
            MembershipFreeze.membership_id == membership.id,
            MembershipFreeze.gym_id == ctx.gym_id,
        )
    )
    if row is None:
        raise not_found("No such freeze.")
    ms.unfreeze(db, ctx, membership, row, request=request)
    db.commit()
    return membership_read_one(db, membership)


@router.post("/{membership_id}/cancel", response_model=SaleResult)
def cancel(
    membership_id: uuid.UUID,
    payload: CancelIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_CANCEL)),
) -> SaleResult:
    """Reason required; a refund, if any, is recorded as a refund payment."""
    membership = load_membership(db, ctx, membership_id)
    refund = ms.PaymentIn(**payload.refund.model_dump()) if payload.refund else None
    refund_row = ms.cancel(db, ctx, membership, payload.reason, refund, request=request)
    db.commit()
    return SaleResult(
        membership=membership_read_one(db, membership),
        payment=payment_read(refund_row, {ctx.staff.id: ctx.staff.name})
        if refund_row
        else None,
    )


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    membership_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_DELETE)),
) -> Response:
    membership = load_membership(db, ctx, membership_id)
    ms.delete(db, ctx, membership, request=request)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{membership_id}/history", response_model=list[HistoryEntry])
def history(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_VIEW)),
) -> list[HistoryEntry]:
    """Every change to the membership and to the money on it."""
    membership = load_membership(db, ctx, membership_id)
    payment_ids = list(
        db.scalars(select(Payment.id).where(Payment.membership_id == membership.id))
    )
    conditions = [ActivityLog.entity_id == membership.id]
    if payment_ids:
        conditions.append(ActivityLog.entity_id.in_(payment_ids))
    return history_for(db, ctx.gym_id, conditions)
