"""Members' app payments confirmed by the wallet (PLAN.md §20.2).

POST /m/online-payments              start one: plan and the gym's account
GET  /m/online-payments/{id}         how it stands
POST /m/online-payments/{id}/check   ask the wallet now

The checkout page opens in the phone's browser, which has no member session,
so it has routes of its own, by the payment's signed link:

GET  /pay/{token}                    the payment and what to do next
POST /pay/{token}/check              back from the wallet: ask it
POST /pay/{token}/pretend            the console wallet's Pay or Cancel
                                     (development and tests only)
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_member
from app.core.errors import not_found
from app.db.session import get_db
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    ONLINE_STARTED,
    REQUEST_APPROVED,
    REQUEST_PENDING,
    OnlinePayment,
    PaymentRequest,
)
from app.models.plan import Plan
from app.schemas.member_app import (
    Checkout,
    OnlinePaymentIn,
    OnlinePaymentRead,
    PayPage,
    PretendIn,
)
from app.services import online_payments as service

member_router = APIRouter(prefix="/m/online-payments", tags=["member app"])
public_router = APIRouter(prefix="/pay", tags=["member app"])


def _read(db: Session, row: OnlinePayment) -> OnlinePaymentRead:
    plan = db.get(Plan, row.plan_id)
    request = (
        db.get(PaymentRequest, row.payment_request_id)
        if row.payment_request_id
        else None
    )
    return OnlinePaymentRead(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        provider=row.provider,
        amount=row.amount,
        plan_name=plan.name if plan else "",
        test=row.test,
        pay_url=service.pay_url(row),
        paid_at=row.paid_at,
        expires_at=row.expires_at,
        approved=request is not None and request.status == REQUEST_APPROVED,
        waiting_for_desk=request is not None and request.status == REQUEST_PENDING,
    )


def _own(db: Session, member: Member, payment_id: uuid.UUID) -> OnlinePayment:
    row = db.get(OnlinePayment, payment_id)
    if row is None or row.member_id != member.id:
        raise not_found("No such payment.")
    return row


@member_router.post(
    "", response_model=OnlinePaymentRead, status_code=status.HTTP_201_CREATED
)
def start(
    payload: OnlinePaymentIn,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> OnlinePaymentRead:
    """Nothing is paid yet: the member pays on the wallet's page next. A
    second start leaves the first open; if both are paid, the desk decides."""
    try:
        row = service.start(
            db,
            member,
            plan_id=payload.plan_id,
            payment_method_id=payload.payment_method_id,
            from_app=payload.from_app,
            return_to=payload.return_to,
        )
    except service.StartFailed as failed:
        db.commit()  # the failed attempt, and the account's trouble
        raise failed.error from None
    answer = _read(db, row)
    db.commit()
    return answer


@member_router.get("/{payment_id}", response_model=OnlinePaymentRead)
def get_one(
    payment_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> OnlinePaymentRead:
    return _read(db, _own(db, member, payment_id))


@member_router.post("/{payment_id}/check", response_model=OnlinePaymentRead)
def check_own(
    payment_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> OnlinePaymentRead:
    row = service.check(db, _own(db, member, payment_id).id)
    db.commit()
    return _read(db, row)


# --- the checkout page, by its link -----------------------------------------------


def _by_token(db: Session, token: str) -> OnlinePayment:
    row = service.from_token(db, token)
    if row is None:
        raise not_found("This payment link has expired.")
    return row


def _page(db: Session, row: OnlinePayment) -> PayPage:
    gym = db.get(Gym, row.gym_id)
    assert gym is not None
    checkout = row.details.get("checkout")
    return PayPage(
        **_read(db, row).model_dump(),
        gym_name=gym.name,
        gym_slug=gym.slug,
        from_app=bool(row.details.get("from_app")),
        return_to=row.details.get("return_to"),
        checkout=Checkout(**checkout)
        if checkout and row.status == ONLINE_STARTED
        else None,
    )


@public_router.get("/{token}", response_model=PayPage)
def page(token: str, db: Session = Depends(get_db)) -> PayPage:
    return _page(db, _by_token(db, token))


@public_router.post("/{token}/check", response_model=PayPage)
def check(token: str, db: Session = Depends(get_db)) -> PayPage:
    """Back from the wallet, or the QR's page asking: the wallet is asked,
    never told. What the browser brings back is not used."""
    row = service.check(db, _by_token(db, token).id)
    db.commit()
    return _page(db, row)


@public_router.post("/{token}/pretend", response_model=PayPage)
def pretend(token: str, payload: PretendIn, db: Session = Depends(get_db)) -> PayPage:
    """The console wallet (GATEWAY_PROVIDER=console): Pay or Cancel."""
    row = service.pretend(db, _by_token(db, token), payload.paid)
    db.commit()
    return _page(db, row)
