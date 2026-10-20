"""Freezing a membership, asked for from the member app (PLAN.md §16.3, 8.6).

The member picks the dates and says why; staff with "Freeze" approve it —
which makes an ordinary freeze, exactly as at the desk — or reject it with a
reason the member sees. One request waits at a time.
"""

import datetime as dt
import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.calendar import format_date
from app.core.errors import AppError
from app.core.time import today_in_nepal, utcnow
from app.core.whatsapp_templates import WhatsApp
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    REQUEST_APPROVED,
    REQUEST_PENDING,
    REQUEST_REJECTED,
    REQUEST_WITHDRAWN,
    FreezeRequest,
)
from app.models.membership import Membership
from app.models.messaging import SMS_MEMBERSHIP
from app.services import activity, live
from app.services import memberships as ms
from app.services.push import service as push
from app.services.push import staff as staff_push

# Long enough for a trip home for Dashain; staff can freeze longer at the desk.
MAX_DAYS = 90


def _changed(db: Session, row: FreezeRequest) -> None:
    """The staff list and badge, and the member's own app."""
    live.publish(
        db, gym_id=row.gym_id, kind=live.FREEZE_REQUEST, member_id=row.member_id
    )


def _pending(row: FreezeRequest) -> None:
    if row.status != REQUEST_PENDING:
        raise AppError(
            409, "request_closed", "This request has already been dealt with."
        )


def create(
    db: Session,
    member: Member,
    *,
    from_date: dt.date,
    to_date: dt.date,
    reason: str,
    request: Request | None = None,
) -> FreezeRequest:
    today = today_in_nepal()
    if from_date < today:
        raise AppError(422, "bad_dates", "A freeze can't start in the past.")
    if to_date < from_date:
        raise AppError(422, "bad_dates", "The freeze ends before it starts.")
    if (to_date - from_date).days + 1 > MAX_DAYS:
        raise AppError(
            422, "freeze_too_long", f"Ask at the desk for more than {MAX_DAYS} days."
        )
    waiting = db.scalar(
        select(FreezeRequest.id).where(
            FreezeRequest.member_id == member.id,
            FreezeRequest.status == REQUEST_PENDING,
        )
    )
    if waiting:
        raise AppError(409, "request_waiting", "You already have a request waiting.")
    membership = db.scalars(
        select(Membership)
        .where(
            Membership.member_id == member.id,
            Membership.gym_id == member.gym_id,
            Membership.cancelled_at.is_(None),
            Membership.start_date <= from_date,
            Membership.end_date >= from_date,
        )
        .order_by(Membership.start_date.desc())
    ).first()
    if membership is None:
        raise AppError(
            422, "no_membership", "You don't have a membership on the first day."
        )
    row = FreezeRequest(
        gym_id=member.gym_id,
        member_id=member.id,
        membership_id=membership.id,
        from_date=from_date,
        to_date=to_date,
        reason=reason.strip(),
    )
    db.add(row)
    db.flush()
    activity.member_action(
        db,
        member,
        "freeze_request.created",
        entity="freeze_request",
        entity_id=row.id,
        changes={"from": from_date, "to": to_date},
        reason=row.reason,
        request=request,
    )
    _changed(db, row)
    # On the phones of staff who freeze, not only their open screens (§18.6).
    staff_push.freeze_request(db, row)
    return row


def withdraw(db: Session, member: Member, row: FreezeRequest) -> None:
    _pending(row)
    row.status = REQUEST_WITHDRAWN
    activity.member_action(
        db,
        member,
        "freeze_request.withdrawn",
        entity="freeze_request",
        entity_id=row.id,
    )
    _changed(db, row)


def _tell(
    db: Session, gym: Gym, member: Member, text: str, template: str, **values: str
) -> None:
    push.notify(
        db,
        gym,
        member,
        title=gym.name,
        body=text[:1].upper() + text[1:],
        url=f"/{gym.slug}/freeze",
        tag="freeze_request",
        sms_body=f"{gym.name}: {text}",
        sms_kind=SMS_MEMBERSHIP,
        whatsapp=WhatsApp(
            template,
            {"name": member.name.split()[0], "gym": gym.name, **values},
            button=f"{gym.slug}/freeze",
        ),
    )


def approve(
    db: Session,
    ctx: StaffContext,
    row: FreezeRequest,
    *,
    request: Request | None = None,
) -> FreezeRequest:
    """`row` loaded FOR UPDATE, so two staff can't freeze it twice."""
    _pending(row)
    membership = db.scalars(
        select(Membership).where(Membership.id == row.membership_id).with_for_update()
    ).one()
    freeze = ms.freeze(
        db, ctx, membership, row.from_date, row.to_date, row.reason, request=request
    )
    row.status = REQUEST_APPROVED
    row.freeze_id = freeze.id
    row.reviewed_by = ctx.staff.id
    row.reviewed_at = utcnow()
    activity.staff_action(
        db,
        ctx.staff,
        "freeze_request.approved",
        entity="freeze_request",
        entity_id=row.id,
        changes={"freeze_id": freeze.id},
        request=request,
    )
    gym = db.get(Gym, ctx.gym_id)
    member = db.get(Member, row.member_id)
    assert gym is not None and member is not None
    show = gym.config.date_display
    dates = {
        "from_date": format_date(row.from_date, show),
        "to_date": format_date(row.to_date, show),
        "end_date": format_date(membership.end_date, show),
    }
    _tell(
        db,
        gym,
        member,
        f"your membership is frozen from {dates['from_date']} to "
        f"{dates['to_date']}. It now ends on {dates['end_date']}.",
        "freeze_approved",
        **dates,
    )
    live.member_changed(db, ctx.gym_id, member.id, member.home_branch_id)
    _changed(db, row)
    return row


def reject(
    db: Session,
    ctx: StaffContext,
    row: FreezeRequest,
    reason: str,
    *,
    request: Request | None = None,
) -> FreezeRequest:
    _pending(row)
    row.status = REQUEST_REJECTED
    row.reject_reason = reason
    row.reviewed_by = ctx.staff.id
    row.reviewed_at = utcnow()
    activity.staff_action(
        db,
        ctx.staff,
        "freeze_request.rejected",
        entity="freeze_request",
        entity_id=row.id,
        reason=reason,
        request=request,
    )
    gym = db.get(Gym, ctx.gym_id)
    member = db.get(Member, row.member_id)
    assert gym is not None and member is not None
    _tell(
        db,
        gym,
        member,
        f"we couldn't freeze your membership: {reason}",
        "freeze_not_approved",
        reason=reason,
    )
    _changed(db, row)
    return row


def latest(db: Session, member_id: uuid.UUID) -> FreezeRequest | None:
    return db.scalars(
        select(FreezeRequest)
        .where(FreezeRequest.member_id == member_id)
        .order_by(FreezeRequest.created_at.desc())
    ).first()
