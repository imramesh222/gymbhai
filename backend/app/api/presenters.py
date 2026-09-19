"""Turning rows plus their computed state into API responses."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.member import Member
from app.models.membership import Membership, MembershipFreeze
from app.models.payment import Payment
from app.models.staff import StaffUser
from app.schemas.members import (
    CurrentMembership,
    FreezeRead,
    MemberDetail,
    MemberRead,
    MembershipRead,
)
from app.schemas.money import PaymentRead
from app.services import members as members_service
from app.services import memberships as ms
from app.services import storage
from app.services.members import MemberState


def staff_names(db: Session, ids: Sequence[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(
        select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(wanted))
    )
    return {row.id: row.name for row in rows}


def payment_read(payment: Payment, names: dict[uuid.UUID, str]) -> PaymentRead:
    read = PaymentRead.model_validate(payment)
    read.received_by_name = (
        names.get(payment.received_by) if payment.received_by else None
    )
    return read


def payments_read(db: Session, payments: Sequence[Payment]) -> list[PaymentRead]:
    names = staff_names(db, [p.received_by for p in payments])
    return [payment_read(p, names) for p in payments]


def membership_read(
    membership: Membership,
    freezes: Sequence[MembershipFreeze],
    payments: Sequence[Payment],
) -> MembershipRead:
    read = MembershipRead.model_validate(membership)
    today = today_in_nepal()
    read.status = ms.status_of(membership, freezes, today)
    read.days_left = (
        ms.days_left(membership, today) if read.status in (ms.ACTIVE, ms.FROZEN) else 0
    )
    read.total = ms.amount_due(membership)
    read.paid = ms.net_paid(payments)
    read.dues = ms.dues_of(membership, payments)
    read.freezes = [FreezeRead.model_validate(f) for f in freezes]
    return read


def membership_read_one(db: Session, membership: Membership) -> MembershipRead:
    return membership_read(
        membership,
        ms.freezes_for(db, [membership.id]),
        ms.payments_for(db, [membership.id]),
    )


def member_read(member: Member, state: MemberState) -> MemberRead:
    read = MemberRead.model_validate(member)
    read.photo_url = storage.signed_url(member.photo_key)
    read.status = state.status
    read.valid_until = state.valid_until
    read.days_left = state.days_left
    read.dues = state.dues
    if state.current is not None:
        read.current = CurrentMembership(
            id=state.current.id,
            plan_name=state.current.plan_name,
            start_date=state.current.start_date,
            end_date=state.current.end_date,
        )
    return read


def member_detail(db: Session, member: Member) -> MemberDetail:
    memberships = ms.memberships_of(db, member)
    ids = [m.id for m in memberships]
    freezes = ms.freezes_for(db, ids)
    membership_payments = ms.payments_for(db, ids)
    state = members_service.state(db, member)

    all_payments = list(
        db.scalars(
            select(Payment)
            .where(Payment.member_id == member.id, Payment.gym_id == member.gym_id)
            .order_by(Payment.paid_at.desc())
        )
    )
    base = member_read(member, state)
    return MemberDetail(
        **base.model_dump(),
        memberships=[
            membership_read(
                m,
                [f for f in freezes if f.membership_id == m.id],
                [p for p in membership_payments if p.membership_id == m.id],
            )
            for m in memberships
        ],
        payments=payments_read(db, all_payments),
        renewal_starts_on=ms.renewal_start(db, member),
        first_membership=ms.is_first_membership(db, member),
    )
