"""The member app's API (PLAN.md §5.5, §7 Member app, §8 "Member app").

Public: the gym's name and logo, and asking for / checking a sign-in code.
Everything else takes the member from their token and only ever returns
their own records (§11).
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_member
from app.api.presenters import payments_read
from app.api.routes.freeze_requests import reads as freeze_reads
from app.api.routes.payment_methods import read as method_read
from app.api.routes.plans import branch_ids_for, plans_read
from app.core import qr
from app.core.config import settings
from app.core.errors import AppError, not_found
from app.core.phone import normalize_phone
from app.core.push_keys import public_key
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import get_db
from app.models.activity import ACTOR_MEMBER
from app.models.gym import GYM_ACTIVE, Branch, Gym
from app.models.member import Member
from app.models.member_app import LET_IN, CheckIn, FreezeRequest, PaymentRequest
from app.models.messaging import Notice
from app.models.payment import GymPaymentMethod, Payment
from app.models.plan import Plan
from app.schemas.member_app import (
    CodeRequest,
    CodeRequested,
    CodeVerify,
    EmailChangeIn,
    EmailConfirmIn,
    FreezeRequestIn,
    FreezeRequestRead,
    JoinIn,
    JoinOptions,
    JoinPlan,
    MemberChoice,
    MemberMe,
    MemberPayments,
    MemberSignIn,
    MemberState,
    MyDetailsIn,
    PaymentRequestIn,
    PaymentRequestRead,
    PublicBranch,
    PublicGym,
    PushEndpoint,
    PushStatus,
    PushSubscriptionIn,
    QrIdentity,
    RenewOptions,
    Visit,
)
from app.schemas.messaging import NoticeRead
from app.schemas.money import ReceiptLink
from app.services import activity, checkins, live, member_auth, receipts, storage
from app.services import freeze_requests as freeze_service
from app.services import leads as leads_service
from app.services import members as members_service
from app.services import memberships as ms
from app.services import payment_requests as requests_service
from app.services.push import service as push

router = APIRouter(prefix="/m", tags=["member app"])

REFRESH_COOKIE = "gb_member_refresh"
REFRESH_PATH = f"{settings.api_v1_prefix}/m"

Slug = Annotated[str, Path(max_length=40)]


def _gym_by_slug(db: Session, slug: str) -> Gym:
    gym = db.scalars(select(Gym).where(Gym.slug == slug.lower())).first()
    # Members are never punished for the owner's unpaid bill (§5.7): only a
    # gym we have suspended is hidden.
    if gym is None or gym.status != GYM_ACTIVE:
        raise not_found("No such gym.")
    return gym


def logo_url(gym: Gym) -> str | None:
    return f"{settings.api_v1_prefix}/m/{gym.slug}/logo" if gym.logo_key else None


def public_gym(db: Session, gym: Gym) -> PublicGym:
    branches = db.scalars(
        select(Branch)
        .where(Branch.gym_id == gym.id, Branch.is_active)
        .order_by(Branch.name)
    )
    return PublicGym(
        slug=gym.slug,
        name=gym.name,
        logo_url=logo_url(gym),
        brand_color=gym.brand_color,
        date_display=gym.config.date_display,
        branches=[PublicBranch(id=b.id, name=b.name) for b in branches],
        join_form=gym.config.join_form,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.member_refresh_days * 24 * 3600,
        path=REFRESH_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def visits_and_streak(db: Session, member: Member) -> tuple[int, int]:
    """Visits this month, and how many weeks in a row with at least one."""
    today = today_in_nepal()
    days = {
        at.astimezone(NEPAL).date()
        for at in db.scalars(
            select(CheckIn.at).where(
                CheckIn.member_id == member.id,
                CheckIn.result.in_(LET_IN),
                CheckIn.at >= utcnow() - dt.timedelta(days=366),
            )
        )
    }
    this_month = sum(1 for d in days if d.year == today.year and d.month == today.month)
    weeks = {d - dt.timedelta(days=d.weekday()) for d in days}
    streak = 0
    week = today - dt.timedelta(days=today.weekday())
    if week not in weeks:
        week -= dt.timedelta(days=7)  # this week isn't over yet
    while week in weeks:
        streak += 1
        week -= dt.timedelta(days=7)
    return this_month, streak


def member_notices(db: Session, member: Member):
    return select(Notice).where(
        Notice.gym_id == member.gym_id,
        or_(Notice.branch_id.is_(None), Notice.branch_id == member.home_branch_id),
    )


def build_me(db: Session, member: Member) -> MemberMe:
    gym = db.get(Gym, member.gym_id)
    assert gym is not None
    state = members_service.state(db, member)
    visits, streak = visits_and_streak(db, member)
    latest = db.scalars(
        member_notices(db, member).order_by(Notice.published_at.desc()).limit(1)
    ).first()
    return MemberMe(
        id=member.id,
        name=member.name,
        member_code=member.member_code,
        phone=member.phone,
        email=member.email,
        photo_url=storage.signed_url(member.photo_key),
        home_branch_id=member.home_branch_id,
        state=MemberState(
            status=state.status,
            plan_name=state.current.plan_name if state.current else None,
            valid_until=state.valid_until,
            days_left=state.days_left,
            dues=state.dues,
            visit_limit=state.visit_limit,
            visits_left=state.visits_left,
            access_hours=state.current.access_hours if state.current else None,
        ),
        qr=QrIdentity(
            member_hex=member.id.hex,
            key=qr.app_key(member.qr_secret, member.qr_version),
            version=member.qr_version,
            window_seconds=qr.WINDOW_SECONDS,
        ),
        gym=public_gym(db, gym),
        visits_this_month=visits,
        streak_weeks=streak,
        latest_notice=NoticeRead.model_validate(latest) if latest else None,
        emergency_contact=member.emergency_contact,
        language=member.language or gym.config.language,
        own_language=member.language,
        digits=gym.config.digits,
        busy=checkins.busyness(db, gym.id, member.home_branch_id)
        if gym.config.show_busyness
        else None,
    )


def _signed_in(
    db: Session, issued: member_auth.Issued, response: Response
) -> MemberSignIn:
    if issued.refresh_token:
        _set_cookie(response, issued.refresh_token)
    return MemberSignIn(
        access_token=issued.access_token,
        expires_in=settings.access_token_minutes * 60,
        me=build_me(db, issued.member),
    )


# --- public ------------------------------------------------------------------------


@router.get("/{slug}/gym", response_model=PublicGym)
def gym_info(slug: Slug, db: Session = Depends(get_db)) -> PublicGym:
    return public_gym(db, _gym_by_slug(db, slug))


@router.get("/{slug}/logo")
def gym_logo(slug: Slug, db: Session = Depends(get_db)) -> Response:
    """Public on purpose: the installed app's icon on the home screen."""
    gym = _gym_by_slug(db, slug)
    data = storage.read(gym.logo_key) if gym.logo_key else None
    if data is None:
        raise not_found("No logo.")
    extension = (gym.logo_key or "").rsplit(".", 1)[-1]
    return Response(
        content=data,
        media_type=storage.CONTENT_TYPES.get(extension, "image/png"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


# --- the public join form (PLAN.md §16.4, 9.5) ---


def _joinable(db: Session, slug: str) -> Gym:
    gym = _gym_by_slug(db, slug)
    if not gym.config.join_form:
        raise not_found("Not found.")
    return gym


@router.get("/{slug}/join", response_model=JoinOptions)
def join_options(slug: Slug, db: Session = Depends(get_db)) -> JoinOptions:
    """The plans to ask about. Not found while the gym has the form off."""
    gym = _joinable(db, slug)
    plans = db.scalars(
        select(Plan)
        .where(Plan.gym_id == gym.id, Plan.is_active)
        .order_by(Plan.sort_order, Plan.name)
    )
    return JoinOptions(
        plans=[JoinPlan(id=p.id, name=p.name, price=p.price) for p in plans]
    )


@router.post("/{slug}/join", status_code=status.HTTP_202_ACCEPTED)
def ask_to_join(
    slug: Slug, payload: JoinIn, request: Request, db: Session = Depends(get_db)
) -> dict[str, bool]:
    gym = _joinable(db, slug)
    try:
        phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise AppError(422, "bad_phone", str(exc)) from exc
    branch_id = payload.branch_id
    if branch_id is not None:
        branch = db.get(Branch, branch_id)
        if branch is None or branch.gym_id != gym.id or not branch.is_active:
            branch_id = None
    leads_service.from_join_form(
        db,
        gym,
        {**payload.model_dump(), "phone": phone, "branch_id": branch_id},
        activity.client_ip(request),
    )
    db.commit()
    return {"received": True}


@router.post("/{slug}/otp/request", response_model=CodeRequested)
def request_code(
    slug: Slug, payload: CodeRequest, request: Request, db: Session = Depends(get_db)
) -> CodeRequested:
    gym = _gym_by_slug(db, slug)
    where = member_auth.destination(payload.phone, payload.email)
    member_auth.request_code(db, gym, where, request)
    shown = (
        f"{where.value[:3]}xxxx{where.value[-3:]}"
        if where.channel == "sms"
        else f"{where.value[0]}…@{where.value.split('@')[1]}"
    )
    return CodeRequested(
        channel=where.channel, sent_to=shown, expires_in=settings.otp_minutes * 60
    )


@router.post("/{slug}/otp/verify", response_model=MemberSignIn)
def verify_code(
    slug: Slug,
    payload: CodeVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MemberSignIn:
    gym = _gym_by_slug(db, slug)
    where = member_auth.destination(payload.phone, payload.email)
    row = member_auth.check_code(db, gym, where, payload.code)
    members = member_auth.members_at(db, gym, where)
    if not members:
        raise member_auth.not_registered(gym)
    if payload.member_id is None and len(members) > 1:
        # "Who are you?" — the code stays good for the second step.
        return MemberSignIn(
            choose=[MemberChoice(id=m.id, name=m.name) for m in members]
        )
    member = (
        next((m for m in members if m.id == payload.member_id), None)
        if payload.member_id
        else members[0]
    )
    if member is None:
        raise AppError(422, "not_on_this_number", "Choose one of the names shown.")
    row.consumed_at = utcnow()
    issued = member_auth.start_session(db, member, request)
    if member_auth.is_master_code(payload.code):
        # Who used the shared code, and from where (PLAN.md §11).
        activity.record(
            db,
            gym_id=gym.id,
            actor_type=ACTOR_MEMBER,
            actor_id=member.id,
            action="member.signed_in_with_master_code",
            entity="member",
            entity_id=member.id,
            request=request,
        )
    db.commit()
    return _signed_in(db, issued, response)


@router.post("/auth/refresh", response_model=MemberSignIn)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    gb_member_refresh: str | None = Cookie(default=None),
) -> MemberSignIn | JSONResponse:
    issued = member_auth.refresh(db, gb_member_refresh)
    if issued is None:
        db.rollback()
        ended = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "You have been signed out.", "code": "session_ended"},
        )
        ended.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
        return ended
    db.commit()
    return _signed_in(db, issued, response)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: Session = Depends(get_db),
    gb_member_refresh: str | None = Cookie(default=None),
) -> Response:
    member_auth.revoke(db, gb_member_refresh)
    db.commit()
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    done.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return done


# --- signed in ---------------------------------------------------------------------


@router.get("/me", response_model=MemberMe)
def me(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> MemberMe:
    return build_me(db, member)


@router.get("/live")
def my_live(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> StreamingResponse:
    """Updates to this member's own membership, payments and visits."""
    accepts = live.member_filter(member.id)
    db.close()  # see app/api/routes/live.py
    return StreamingResponse(
        live.stream(accepts, seconds=settings.access_token_minutes * 60),
        media_type="text/event-stream",
        headers=live.STREAM_HEADERS,
    )


# --- their own details (PLAN.md §16.3, 8.5) ---


@router.patch("/me", response_model=MemberMe)
def update_me(
    payload: MyDetailsIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> MemberMe:
    changes = payload.model_dump(exclude_unset=True)
    if "emergency_contact" in changes:
        changes["emergency_contact"] = (
            changes["emergency_contact"] or ""
        ).strip() or None
    members_service.update_by_member(db, member, changes, request=request)
    db.commit()
    return build_me(db, member)


@router.post("/me/email", status_code=status.HTTP_204_NO_CONTENT)
def change_email(
    payload: EmailChangeIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> Response:
    """A code to the new address; it is theirs once they type it."""
    gym = db.get(Gym, member.gym_id)
    assert gym is not None
    member_auth.request_email_change(db, gym, member, str(payload.email), request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/email/confirm", response_model=MemberMe)
def confirm_email(
    payload: EmailConfirmIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> MemberMe:
    gym = db.get(Gym, member.gym_id)
    assert gym is not None
    address = member_auth.confirm_email_change(
        db, gym, member, str(payload.email), payload.code
    )
    members_service.update_by_member(
        db, member, {"email": address}, action="member.email_changed", request=request
    )
    db.commit()
    return build_me(db, member)


@router.post("/me/photo", response_model=MemberMe)
async def change_my_photo(
    request: Request,
    file: UploadFile = File(...),
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> MemberMe:
    """The face the desk checks against the card (§4.2): the member's own."""
    data = await file.read(storage.MAX_BYTES + 1)
    key = storage.put(
        storage.new_key(member.gym_id, "members", storage.sniff_image(data)), data
    )
    old = member.photo_key
    members_service.update_by_member(
        db, member, {"photo_key": key}, action="member.photo_changed", request=request
    )
    db.commit()
    storage.delete(old)
    return build_me(db, member)


# --- freeze requests (PLAN.md §16.3, 8.6) ---


@router.get("/freeze-requests/latest", response_model=FreezeRequestRead | None)
def my_freeze_request(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> FreezeRequestRead | None:
    """Their newest: waiting, or the answer to it."""
    row = freeze_service.latest(db, member.id)
    return freeze_reads(db, [row])[0] if row else None


@router.post(
    "/freeze-requests",
    response_model=FreezeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def ask_to_freeze(
    payload: FreezeRequestIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> FreezeRequestRead:
    row = freeze_service.create(
        db,
        member,
        from_date=payload.from_date,
        to_date=payload.to_date,
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return freeze_reads(db, [row])[0]


@router.post(
    "/freeze-requests/{freeze_request_id}/withdraw", response_model=FreezeRequestRead
)
def withdraw_freeze_request(
    freeze_request_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> FreezeRequestRead:
    row = db.scalars(
        select(FreezeRequest)
        .where(
            FreezeRequest.id == freeze_request_id, FreezeRequest.member_id == member.id
        )
        .with_for_update()
    ).first()
    if row is None:
        raise not_found("No such request.")
    freeze_service.withdraw(db, member, row)
    db.commit()
    return freeze_reads(db, [row])[0]


# --- push (PLAN.md §16.3, 8.3) ---


@router.get("/me/push", response_model=PushStatus)
def my_push(
    endpoint: Annotated[str | None, Query(max_length=2000)] = None,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PushStatus:
    rows = push.live(db, member.id)
    return PushStatus(
        public_key=public_key(),
        subscribed=any(endpoint is None or r.endpoint == endpoint for r in rows),
    )


@router.post("/me/push", response_model=PushStatus)
def turn_push_on(
    payload: PushSubscriptionIn,
    request: Request,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PushStatus:
    """This phone takes reminders, notices and answers now, instead of SMS."""
    if not push.available():
        raise AppError(409, "push_unavailable", "Notifications aren't set up yet.")
    row = push.subscribe(
        db,
        member,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    activity.member_action(
        db, member, "push.subscribed", entity="push_subscription", entity_id=row.id
    )
    db.commit()
    return PushStatus(public_key=public_key(), subscribed=True)


@router.post("/me/push/off", response_model=PushStatus)
def turn_push_off(
    payload: PushEndpoint,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PushStatus:
    """This phone stops: on "Turn off", and on signing out."""
    if push.unsubscribe(db, member, payload.endpoint):
        activity.member_action(db, member, "push.unsubscribed")
    db.commit()
    return PushStatus(public_key=public_key(), subscribed=False)


@router.get("/me/payments", response_model=MemberPayments)
def my_payments(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> MemberPayments:
    payments = db.scalars(
        select(Payment)
        .where(Payment.member_id == member.id, Payment.voided_at.is_(None))
        .order_by(Payment.paid_at.desc())
    )
    requests = db.scalars(
        select(PaymentRequest)
        .where(PaymentRequest.member_id == member.id)
        .order_by(PaymentRequest.created_at.desc())
        .limit(20)
    ).all()
    return MemberPayments(
        dues=ms.member_dues(db, member),
        payments=payments_read(db, list(payments)),
        requests=requests_read(db, requests),
    )


@router.post("/me/payments/{payment_id}/receipt-link", response_model=ReceiptLink)
def my_receipt_link(
    payment_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> ReceiptLink:
    """Payments → Download receipt, for the member's own payments only."""
    payment = db.get(Payment, payment_id)
    if payment is None or payment.member_id != member.id:
        raise not_found("Receipt not found.")
    return receipts.share(receipts.build(db, payment))


@router.get("/me/visits", response_model=list[Visit])
def my_visits(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> list[Visit]:
    today = today_in_nepal()
    try:
        year, number = (int(x) for x in (month or f"{today:%Y-%m}").split("-"))
        first = dt.date(year, number, 1)
    except ValueError as exc:
        raise AppError(422, "bad_month", "Month must look like 2026-09.") from exc
    after = dt.date(year + number // 12, number % 12 + 1, 1)
    rows = db.execute(
        select(CheckIn.at, CheckIn.result, Branch.name)
        .join(Branch, Branch.id == CheckIn.branch_id)
        .where(
            CheckIn.member_id == member.id,
            CheckIn.result.in_(LET_IN),
            CheckIn.at >= dt.datetime.combine(first, dt.time(), tzinfo=NEPAL),
            CheckIn.at < dt.datetime.combine(after, dt.time(), tzinfo=NEPAL),
        )
        .order_by(CheckIn.at.desc())
    )
    return [Visit(at=at, result=result, branch_name=name) for at, result, name in rows]


@router.get("/notices", response_model=list[NoticeRead])
def my_notices(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> list[Notice]:
    return list(
        db.scalars(
            member_notices(db, member).order_by(Notice.published_at.desc()).limit(50)
        )
    )


@router.get("/renew", response_model=RenewOptions)
def renew_options(
    member: Member = Depends(current_member), db: Session = Depends(get_db)
) -> RenewOptions:
    """Plans with prices, and the gym's own accounts to pay into (§7 Renew)."""
    plans = db.scalars(
        select(Plan)
        .where(Plan.gym_id == member.gym_id, Plan.is_active, Plan.price.is_not(None))
        .order_by(Plan.sort_order, Plan.created_at)
    ).all()
    branches = branch_ids_for(db, plans)
    visible = [
        p for p in plans if p.all_branches or member.home_branch_id in branches[p.id]
    ]
    methods = db.scalars(
        select(GymPaymentMethod)
        .where(GymPaymentMethod.gym_id == member.gym_id, GymPaymentMethod.is_active)
        .order_by(GymPaymentMethod.sort_order)
    )
    return RenewOptions(
        plans=plans_read(db, visible),
        payment_methods=[method_read(m) for m in methods],
        renewal_starts_on=ms.renewal_start(db, member),
        first_membership=ms.is_first_membership(db, member),
    )


def requests_read(
    db: Session, rows: Sequence[PaymentRequest]
) -> list[PaymentRequestRead]:
    """Plan names and account labels in two queries, however many rows."""
    plan_names = dict(
        db.execute(
            select(Plan.id, Plan.name).where(Plan.id.in_({r.plan_id for r in rows}))
        ).all()
    )
    method_ids = {r.payment_method_id for r in rows if r.payment_method_id}
    labels = (
        dict(
            db.execute(
                select(GymPaymentMethod.id, GymPaymentMethod.label).where(
                    GymPaymentMethod.id.in_(method_ids)
                )
            ).all()
        )
        if method_ids
        else {}
    )
    reads = []
    for row in rows:
        read = PaymentRequestRead.model_validate(row)
        read.screenshot_url = storage.signed_url(row.screenshot_key)
        read.plan_name = plan_names.get(row.plan_id)
        if row.payment_method_id:
            read.method_label = labels.get(row.payment_method_id)
        reads.append(read)
    return reads


def request_read(db: Session, row: PaymentRequest) -> PaymentRequestRead:
    return requests_read(db, [row])[0]


def _own_request(db: Session, member: Member, request_id: uuid.UUID) -> PaymentRequest:
    """Locked, like the staff side: withdrawing races approving."""
    row = db.get(
        PaymentRequest, request_id, with_for_update=True, populate_existing=True
    )
    if row is None or row.member_id != member.id:
        raise not_found("No such request.")
    return row


@router.post(
    "/payment-requests",
    response_model=PaymentRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_request(
    payload: PaymentRequestIn,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PaymentRequestRead:
    """ "I've paid" — waiting for the gym to confirm (§5.2)."""
    row = requests_service.create(
        db,
        member,
        plan_id=payload.plan_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        transaction_ref=payload.transaction_ref,
    )
    db.commit()
    return request_read(db, row)


@router.post(
    "/payment-requests/{request_id}/screenshot", response_model=PaymentRequestRead
)
async def upload_screenshot(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PaymentRequestRead:
    row = _own_request(db, member, request_id)
    if row.status != "pending":
        raise AppError(
            409, "request_closed", "This request has already been dealt with."
        )
    data = await file.read(storage.MAX_BYTES + 1)
    key = storage.put(
        storage.new_key(
            member.gym_id, "payment-screenshots", storage.sniff_image(data)
        ),
        data,
    )
    old, row.screenshot_key = row.screenshot_key, key
    db.commit()
    storage.delete(old)
    return request_read(db, row)


@router.post(
    "/payment-requests/{request_id}/withdraw", response_model=PaymentRequestRead
)
def withdraw_request(
    request_id: uuid.UUID,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> PaymentRequestRead:
    row = _own_request(db, member, request_id)
    requests_service.withdraw(db, row)
    db.commit()
    return request_read(db, row)
