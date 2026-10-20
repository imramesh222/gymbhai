"""Members' app payments confirmed by the wallet (PLAN.md §20.2).

The gym's own eSewa, Khalti or Fonepay merchant account is paid; we only ask
the wallet whether it was. Once it says so the payment becomes a payment
request, approved by itself exactly as the desk would approve it (§5.4). When
it can't be approved by itself (the plan changed, the member started another
payment, the amounts differ) the request waits on Payment requests, marked as
confirmed by the wallet, for the desk to finish.

Checking a payment locks its row, so the member landing back, the Fonepay
screen asking, and the worker can't approve one payment twice.
"""

import datetime as dt
import logging
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core import sealed, signed_links
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import ALL_PERMISSIONS
from app.core.time import utcnow
from app.models.activity import ACTOR_SYSTEM
from app.models.gym import Gym
from app.models.member import Member
from app.models.member_app import (
    ONLINE_EXPIRED,
    ONLINE_FAILED,
    ONLINE_PAID,
    ONLINE_STARTED,
    REQUEST_PENDING,
    OnlinePayment,
    PaymentRequest,
)
from app.models.payment import GymPaymentMethod
from app.models.plan import Plan
from app.models.staff import StaffUser
from app.services import activity, live
from app.services import memberships as ms
from app.services import payment_requests as requests
from app.services.gateways import providers
from app.services.gateways.providers import (
    FAILED,
    PAID,
    WALLETS,
    Answer,
    Checkout,
    GatewayError,
    Keys,
    KeysRefused,
    Order,
)
from app.services.push import staff as staff_push

log = logging.getLogger("gymbhai.payments")

# How long a payment is checked for. Khalti's page lasts an hour; eSewa says
# to ask its status after five minutes if nothing came back.
LASTS = dt.timedelta(hours=2)
# The worker's checks: soon, then less often.
CHECK_AFTER_MINUTES = (1, 1, 2, 3, 5, 10, 15, 20, 30, 30, 60)
# The wallet unreachable for this long past the end: we stop asking.
GIVE_UP_AFTER = dt.timedelta(hours=22)
TOKEN_DAYS = 1
JOB_CHECK = "online_payment.check"
LABELS = {"esewa": "eSewa", "khalti": "Khalti", "fonepay": "Fonepay"}


def available() -> bool:
    """Whether wallets can confirm payments here at all. On a server only
    with GATEWAY_PROVIDER=live: the console there would confirm nothing real."""
    return settings.gateway_provider == "live" or settings.environment in (
        "local",
        "test",
    )


def online(method: GymPaymentMethod) -> bool:
    """This account confirms its members' payments by itself."""
    return (
        available()
        and method.kind in WALLETS
        and method.gateway_secret is not None
        and method.is_active
    )


def keys_of(method: GymPaymentMethod) -> Keys:
    assert method.gateway_secret is not None
    try:
        secret = sealed.open_sealed(method.gateway_secret, method.id)
    except sealed.Unreadable as exc:
        # GATEWAY_KEY changed: the owner must enter the keys again.
        raise KeysRefused("The keys can't be read: enter them again.") from exc
    return Keys(
        merchant=method.gateway_merchant, secret=secret, test=method.gateway_test
    )


def hint(method: GymPaymentMethod) -> str | None:
    """The last four characters of the secret key, to recognise it by."""
    if method.gateway_secret is None:
        return None
    try:
        key = sealed.open_sealed(method.gateway_secret, method.id).get("secret_key")
    except sealed.Unreadable:
        return None
    return key[-4:] if key else None


def set_keys(
    method: GymPaymentMethod,
    *,
    merchant: str | None,
    secret: dict[str, str],
    test: bool,
) -> None:
    method.gateway_merchant = merchant
    method.gateway_secret = sealed.seal(secret, method.id)
    method.gateway_test = test
    method.gateway_ok_at = None
    method.gateway_error = None


def clear_keys(method: GymPaymentMethod) -> None:
    method.gateway_merchant = None
    method.gateway_secret = None
    method.gateway_test = False
    method.gateway_ok_at = None
    method.gateway_error = None


class StartFailed(Exception):
    """The wallet wouldn't start the payment. The caller commits (the failed
    attempt, and the account's trouble for Settings) and raises `error`."""

    def __init__(self, error: AppError) -> None:
        super().__init__(error.code)
        self.error = error


def _gateway(method_kind: str) -> providers.Gateway:
    return providers.gateway(method_kind, settings.gateway_provider)


def system_context(gym_id: uuid.UUID, provider: str) -> StaffContext:
    """GymBhai acting for the gym when a wallet confirms a payment: every
    permission, every branch. Its stand-in staff has no id, so nothing it
    does is written as anyone's (activity.staff_action records the system)."""
    staff = StaffUser(gym_id=gym_id, name=LABELS.get(provider, provider))
    return StaffContext(
        staff=staff, gym_id=gym_id, permissions=ALL_PERMISSIONS, branch_ids=None
    )


# --- links ------------------------------------------------------------------------


def token_for(row: OnlinePayment) -> str:
    """The checkout page's own link: the phone's browser has no session."""
    expires, signature = signed_links.sign("pay", row.id, TOKEN_DAYS)
    return f"{row.id}.{expires}.{signature}"


def from_token(db: Session, token: str) -> OnlinePayment | None:
    try:
        raw_id, raw_expires, signature = token.split(".", 2)
        row_id, expires = uuid.UUID(raw_id), int(raw_expires)
    except ValueError:
        return None
    if not signed_links.valid("pay", row_id, expires, signature):
        return None
    return db.get(OnlinePayment, row_id)


def pay_url(row: OnlinePayment) -> str:
    return f"{settings.public_app_url.rstrip('/')}/pay/{token_for(row)}"


def _order(db: Session, row: OnlinePayment) -> Order:
    member = db.get(Member, row.member_id)
    gym = db.get(Gym, row.gym_id)
    plan = db.get(Plan, row.plan_id)
    assert member is not None and gym is not None and plan is not None
    page = pay_url(row)
    return Order(
        id=row.order_id,
        amount=row.amount,
        name=f"{plan.name}, {gym.name}"[:100],
        # eSewa adds "?data=…" to the address it's given: no query of our own.
        return_url=f"{page}/back",
        failure_url=f"{page}/cancelled",
        website_url=settings.public_app_url,
        customer_name=member.name,
        customer_phone=member.phone,
    )


# --- starting -----------------------------------------------------------------------


def start(
    db: Session,
    member: Member,
    *,
    plan_id: uuid.UUID,
    payment_method_id: uuid.UUID,
    from_app: bool = False,
    return_to: str | None = None,
) -> OnlinePayment:
    """A payment for a plan through one of the gym's merchant accounts. The
    amount is the plan's price and any admission fees: the member can't
    change it, and there's no part payment."""
    method = db.get(GymPaymentMethod, payment_method_id)
    if method is None or method.gym_id != member.gym_id or not online(method):
        raise AppError(
            422, "bad_method", "That account can't take payments in the app."
        )
    plan, with_ids = requests.renewal_plan(db, member, plan_id)
    assert plan.price is not None
    ms.lock_member(db, member)
    requests.ensure_none_pending(db, member)
    now = utcnow()
    row = OnlinePayment(
        id=uuid.uuid4(),
        gym_id=member.gym_id,
        member_id=member.id,
        plan_id=plan.id,
        payment_method_id=method.id,
        provider=method.kind,
        # The wallet's test system: no real money, so nothing is sold.
        test=method.gateway_test and settings.gateway_provider == "live",
        amount=plan.price + requests.admission_for(db, member, plan, with_ids),
        with_member_ids=with_ids,
        status=ONLINE_STARTED,
        order_id=uuid.uuid4().hex[:20].upper(),
        details={"from_app": from_app, "return_to": return_to if from_app else None},
        expires_at=now + LASTS,
    )
    db.add(row)
    db.flush()
    try:
        checkout = _gateway(method.kind).start(keys_of(method), _order(db, row))
    except GatewayError as exc:
        log.warning("%s didn't start a payment: %s", method.kind, exc)
        row.status = ONLINE_FAILED
        row.error = str(exc)[:500]
        if isinstance(exc, KeysRefused):
            # The owner sees why in Settings.
            method.gateway_error = row.error
            raise StartFailed(
                AppError(
                    502,
                    "gateway_keys",
                    f"{LABELS[method.kind]} isn't set up right at the gym. "
                    "Please use the gym's QR, or tell the desk.",
                )
            ) from exc
        raise StartFailed(
            AppError(
                502,
                "gateway_down",
                f"{LABELS[method.kind]} isn't answering. Try again in a minute, "
                "or use the gym's QR.",
            )
        ) from exc
    # An earlier one left open: if it's paid after all, the desk decides.
    db.execute(
        update(OnlinePayment)
        .where(
            OnlinePayment.member_id == member.id,
            OnlinePayment.status == ONLINE_STARTED,
            OnlinePayment.replaced_at.is_(None),
            OnlinePayment.id != row.id,
        )
        .values(replaced_at=now)
    )
    row.provider_ref = checkout.reference
    row.details = {**row.details, "checkout": _checkout_dict(checkout)}
    method.gateway_ok_at = now
    method.gateway_error = None
    _queue_check(db, row)
    activity.member_action(
        db,
        member,
        "online_payment.started",
        entity="online_payment",
        entity_id=row.id,
        changes={"plan_id": plan.id, "amount": row.amount, "provider": row.provider},
    )
    return row


def _checkout_dict(checkout: Checkout) -> dict[str, Any]:
    return {
        "kind": checkout.kind,
        "url": checkout.url,
        "fields": checkout.fields,
        "qr": checkout.qr,
    }


def _queue_check(db: Session, row: OnlinePayment) -> None:
    from app.worker import enqueue

    step = CHECK_AFTER_MINUTES[min(row.checks, len(CHECK_AFTER_MINUTES) - 1)]
    enqueue(
        db,
        JOB_CHECK,
        {"id": str(row.id)},
        run_at=utcnow() + dt.timedelta(minutes=step),
    )


# --- checking -----------------------------------------------------------------------


def check(db: Session, row_id: uuid.UUID, *, queue_next: bool = False) -> OnlinePayment:
    """Ask the wallet, and act on its answer. Locks the payment."""
    row = db.get(OnlinePayment, row_id, with_for_update=True, populate_existing=True)
    assert row is not None
    if row.status != ONLINE_STARTED:
        return row
    now = utcnow()
    method = db.get(GymPaymentMethod, row.payment_method_id)
    assert method is not None
    try:
        if method.gateway_secret is None:
            # Taken off the account since: nothing to ask the wallet with.
            raise GatewayError("The account's keys were removed.")
        answer = _gateway(row.provider).check(
            keys_of(method),
            _order(db, row),
            {**row.details, "reference": row.provider_ref},
        )
    except GatewayError as exc:
        row.error = str(exc)[:500]
        if isinstance(exc, KeysRefused):
            method.gateway_error = row.error
        answer = None
    row.checks += 1
    row.checked_at = now
    if answer is not None:
        row.error = None
        method.gateway_ok_at = now
        method.gateway_error = None
        if answer.status == PAID:
            _paid(db, row, answer)
        elif answer.status == FAILED:
            row.status = ONLINE_FAILED
            row.error = answer.detail
            _changed(db, row)
    # Expired only on the wallet's own word that it isn't paid: while the
    # wallet can't be reached, the money may be there. After a day of that,
    # it's left for someone to look at.
    if row.status == ONLINE_STARTED and (
        (answer is not None and now >= row.expires_at)
        or now >= row.expires_at + GIVE_UP_AFTER
    ):
        row.status = ONLINE_EXPIRED
        _changed(db, row)
    if row.status == ONLINE_STARTED and queue_next:
        _queue_check(db, row)
    return row


def handle_check(db: Session, payload: dict[str, Any]) -> None:
    """The worker's check, for the member who closed the page: queued when
    the payment starts, and again after each check until it's settled."""
    check(db, uuid.UUID(payload["id"]), queue_next=True)


def _paid(db: Session, row: OnlinePayment, answer: Answer) -> None:
    """The wallet has the money: a payment request, approved by itself if
    nothing needs the desk. On the wallet's test system nothing is sold:
    there's no real money, only the keys and the way back proved."""
    now = utcnow()
    row.status = ONLINE_PAID
    row.paid_at = now
    ref = (answer.transaction_ref or f"{row.provider.upper()}-{row.order_id}")[:64]
    row.transaction_ref = ref
    amount = answer.amount if answer.amount is not None else row.amount
    if row.test:
        activity.record(
            db,
            gym_id=row.gym_id,
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            action="online_payment.test_paid",
            entity="online_payment",
            entity_id=row.id,
            changes={
                "provider": row.provider,
                "transaction_ref": ref,
                "amount": amount,
            },
        )
        _changed(db, row)
        return
    member = db.get(Member, row.member_id)
    gym = db.get(Gym, row.gym_id)
    assert member is not None and gym is not None

    ms.lock_member(db, member)
    ms.lock_transaction_ref(db, row.gym_id, ref)
    reused = requests.ref_in_use(db, row.gym_id, ref)
    request = PaymentRequest(
        gym_id=row.gym_id,
        member_id=row.member_id,
        plan_id=row.plan_id,
        payment_method_id=row.payment_method_id,
        amount=amount,
        # Already used in this gym (the desk typed it in by hand): the desk
        # sorts it out, so the request carries none.
        transaction_ref=None if reused else ref,
        status=REQUEST_PENDING,
        with_member_ids=row.with_member_ids,
        confirmed_by=row.provider,
    )
    db.add(request)
    db.flush()
    row.payment_request_id = request.id
    activity.record(
        db,
        gym_id=row.gym_id,
        actor_type=ACTOR_SYSTEM,
        actor_id=None,
        action="online_payment.paid",
        entity="online_payment",
        entity_id=row.id,
        changes={
            "provider": row.provider,
            "transaction_ref": ref,
            "amount": amount,
            "payment_request_id": request.id,
        },
    )
    by_itself = (
        amount == row.amount
        and row.replaced_at is None
        and not reused
        and not _others_pending(db, row, request)
    )
    if by_itself:
        try:
            with db.begin_nested():
                requests.approve(
                    db,
                    system_context(row.gym_id, row.provider),
                    request,
                    note=f"From the member app, confirmed by {LABELS[row.provider]}",
                )
        except AppError as exc:
            # The plan changed since, or someone left the family plan: the
            # money is there, the desk decides how to sell it.
            log.info("payment %s waits for the desk: %s", row.id, exc.code)
            db.refresh(request)
            by_itself = False
    if not by_itself:
        requests._changed(db, request)
        staff_push.payment_request(db, request)
    _changed(db, row)


def _others_pending(db: Session, row: OnlinePayment, request: PaymentRequest) -> bool:
    """Another request waiting for this member (made while this was open)."""
    return bool(
        db.scalar(
            select(PaymentRequest.id).where(
                PaymentRequest.member_id == row.member_id,
                PaymentRequest.status == REQUEST_PENDING,
                PaymentRequest.id != request.id,
            )
        )
    )


def _changed(db: Session, row: OnlinePayment) -> None:
    """The member's own Renew and the checkout page hear it."""
    live.publish(
        db, gym_id=row.gym_id, kind=live.PAYMENT_REQUEST, member_id=row.member_id
    )


def pretend(db: Session, row: OnlinePayment, paid: bool) -> OnlinePayment:
    """The console wallet's *Pay* or *Cancel* (development and tests)."""
    if settings.gateway_provider != "console":
        raise AppError(404, "not_found", "Not found.")
    db.refresh(row, with_for_update=True)
    if row.status == ONLINE_STARTED:
        row.details = {**row.details, "console": PAID if paid else FAILED}
        db.flush()
    return check(db, row.id)
