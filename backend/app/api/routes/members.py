"""Members (PLAN.md §5.3, §5.5, §7).

Adding a member at the desk is what gives them app access; the same screen can
sell their first membership and take payment in one step.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.presenters import (
    member_detail,
    member_read,
    membership_read_one,
    payment_read,
)
from app.api.tenancy import StaffContext, get_in_gym
from app.core import qr
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.phone import normalize_phone
from app.db.session import get_db
from app.models.activity import ActivityLog
from app.models.gym import Gym
from app.models.member import Member
from app.schemas.member_app import AccessIn, CardRead
from app.schemas.members import (
    ArchiveIn,
    HistoryEntry,
    MemberCreate,
    MemberCreated,
    MemberDetail,
    MemberList,
    MemberUpdate,
    PhoneMatch,
    SaleFields,
    SaleResult,
)
from app.services import activity, member_auth, reminders, storage
from app.services import members as members_service
from app.services import memberships as ms
from app.services.history import history_for

router = APIRouter(prefix="/members", tags=["members"])

VIEW = require(Permission.MEMBERS_VIEW)


def load_member(db: Session, ctx: StaffContext, member_id: uuid.UUID) -> Member:
    return get_in_gym(
        db,
        Member,
        member_id,
        ctx,
        branch_column=Member.home_branch_id,
        message="No such member.",
    )


def _config(db: Session, ctx: StaffContext):
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    return gym.config


def _sale(sale: SaleFields) -> ms.SaleIn:
    payment = None
    if sale.payment is not None:
        payment = ms.PaymentIn(**sale.payment.model_dump())
    return ms.SaleIn(**sale.model_dump(exclude={"payment"}), payment=payment)


@router.get("", response_model=MemberList)
def list_members(
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(VIEW),
    q: Annotated[str | None, Query(max_length=120)] = None,
    member_status: Annotated[
        str | None,
        Query(alias="status", pattern="^(active|frozen|upcoming|expired|none)$"),
    ] = None,
    branch_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    has_dues: bool | None = None,
    expiring_within: Annotated[int | None, Query(ge=0, le=90)] = None,
    archived: bool = False,
    sort: Annotated[str, Query(pattern="^(name|code|recent)$")] = "name",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberList:
    """Search by name, phone or code; filter by status, branch, plan and dues."""
    stmt = members_service.search(
        ctx,
        q=q,
        status=member_status,
        branch_id=branch_id,
        plan_id=plan_id,
        has_dues=has_dues,
        expiring_within=expiring_within,
        archived=archived,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {
        "name": (Member.name, Member.member_code),
        "code": (Member.member_code,),
        "recent": (Member.created_at.desc(),),
    }[sort]
    members = list(db.scalars(stmt.order_by(*order).limit(limit).offset(offset)))
    states = members_service.states_for(db, members)
    return MemberList(
        items=[member_read(m, states[m.id]) for m in members], total=total
    )


@router.get("/phone-check", response_model=list[PhoneMatch])
def phone_check(
    phone: Annotated[str, Query(max_length=20)],
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_ADD)),
) -> list[PhoneMatch]:
    """Members already on this number, to warn before adding another (§5.5)."""
    try:
        normalized = normalize_phone(phone)
    except ValueError:
        return []
    return [
        PhoneMatch(id=m.id, name=m.name, member_code=m.member_code)
        for m in members_service.same_phone(db, ctx.gym_id, normalized)
    ]


@router.post("", response_model=MemberCreated, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_ADD)),
) -> MemberCreated:
    if payload.membership is not None and not ctx.can(Permission.MEMBERSHIPS_SELL):
        raise AppError(
            403,
            "permission_denied",
            "You don't have permission to do this.",
            permission=Permission.MEMBERSHIPS_SELL.value,
        )
    config = _config(db, ctx)
    matches = members_service.same_phone(db, ctx.gym_id, payload.phone)
    member = members_service.create(
        db, ctx, payload.model_dump(exclude={"membership"}), config, request=request
    )
    membership = payment = None
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    if payload.membership is not None:
        membership, payment = ms.sell(
            db, ctx, member, _sale(payload.membership), config, request=request
        )
        reminders.after_sale(
            db, gym, member, membership, new_member=True, staff_id=ctx.staff.id
        )
    else:
        reminders.welcome(db, gym, member, ctx.staff.id)
    db.commit()
    return MemberCreated(
        member=member_detail(db, member),
        membership_id=membership.id if membership else None,
        payment_id=payment.id if payment else None,
        same_phone=[
            PhoneMatch(id=m.id, name=m.name, member_code=m.member_code) for m in matches
        ],
    )


@router.get("/{member_id}", response_model=MemberDetail)
def get_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(VIEW),
) -> MemberDetail:
    return member_detail(db, load_member(db, ctx, member_id))


@router.patch("/{member_id}", response_model=MemberDetail)
def update_member(
    member_id: uuid.UUID,
    payload: MemberUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_EDIT)),
) -> MemberDetail:
    member = load_member(db, ctx, member_id)
    members_service.update(
        db, ctx, member, payload.model_dump(exclude_unset=True), request=request
    )
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/archive", response_model=MemberDetail)
def archive_member(
    member_id: uuid.UUID,
    payload: ArchiveIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_ARCHIVE)),
) -> MemberDetail:
    """Hidden from lists; history kept (§5.6)."""
    member = load_member(db, ctx, member_id)
    members_service.update(
        db,
        ctx,
        member,
        {"is_archived": True},
        action="member.archived",
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/unarchive", response_model=MemberDetail)
def unarchive_member(
    member_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_ARCHIVE)),
) -> MemberDetail:
    member = load_member(db, ctx, member_id)
    members_service.update(
        db,
        ctx,
        member,
        {"is_archived": False},
        action="member.unarchived",
        request=request,
    )
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/photo", response_model=MemberDetail)
async def upload_photo(
    member_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_EDIT)),
) -> MemberDetail:
    member = load_member(db, ctx, member_id)
    data = await file.read(storage.MAX_BYTES + 1)
    key = storage.put(
        storage.new_key(ctx.gym_id, "members", storage.sniff_image(data)), data
    )
    old = member.photo_key
    members_service.update(
        db,
        ctx,
        member,
        {"photo_key": key},
        action="member.photo_changed",
        request=request,
    )
    db.commit()
    storage.delete(old)
    return member_detail(db, member)


@router.post(
    "/{member_id}/memberships",
    response_model=SaleResult,
    status_code=status.HTTP_201_CREATED,
)
def sell_membership(
    member_id: uuid.UUID,
    payload: SaleFields,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERSHIPS_SELL)),
) -> SaleResult:
    """A new membership or a renewal, with payment taken now if any (§5.3)."""
    member = load_member(db, ctx, member_id)
    if member.is_archived:
        raise AppError(409, "member_archived", "Restore this member first.")
    membership, payment = ms.sell(
        db, ctx, member, _sale(payload), _config(db, ctx), request=request
    )
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    reminders.after_sale(
        db, gym, member, membership, new_member=False, staff_id=ctx.staff.id
    )
    db.commit()
    return SaleResult(
        membership=membership_read_one(db, membership),
        payment=payment_read(payment, {ctx.staff.id: ctx.staff.name})
        if payment
        else None,
    )


@router.get("/{member_id}/history", response_model=list[HistoryEntry])
def member_history(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(VIEW),
) -> list[HistoryEntry]:
    member = load_member(db, ctx, member_id)
    return history_for(db, ctx.gym_id, [ActivityLog.entity_id == member.id])


# --- app access (PLAN.md §5.5) ----------------------------------------------------

ACCESS = require(Permission.MEMBERS_APP_ACCESS)


@router.patch("/{member_id}/access", response_model=MemberDetail)
def set_app_access(
    member_id: uuid.UUID,
    payload: AccessIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ACCESS),
) -> MemberDetail:
    """Off blocks sign-in and signs out their devices (e.g. a banned member)."""
    member = load_member(db, ctx, member_id)
    members_service.update(
        db,
        ctx,
        member,
        {"app_access": payload.app_access},
        action="member.app_access_changed",
        request=request,
    )
    if not payload.app_access:
        member_auth.sign_out_everywhere(db, member.id)
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/sign-out-all", response_model=MemberDetail)
def sign_out_all(
    member_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ACCESS),
) -> MemberDetail:
    """Lost phone."""
    member = load_member(db, ctx, member_id)
    count = member_auth.sign_out_everywhere(db, member.id)
    activity.staff_action(
        db,
        ctx.staff,
        "member.signed_out_everywhere",
        entity="member",
        entity_id=member.id,
        changes={"sessions": count},
        request=request,
    )
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/resend-welcome", response_model=MemberDetail)
def resend_welcome(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ACCESS),
) -> MemberDetail:
    member = load_member(db, ctx, member_id)
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    reminders.welcome(db, gym, member, ctx.staff.id)
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/qr/reissue", response_model=MemberDetail)
def reissue_qr(
    member_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(ACCESS),
) -> MemberDetail:
    """Lost phone or suspected sharing: every old code and card stops working,
    and the member signs in again for a new one (§4.2)."""
    member = load_member(db, ctx, member_id)
    members_service.update(
        db,
        ctx,
        member,
        {
            "qr_version": member.qr_version + 1,
            "card_token": members_service.new_card_token(),
        },
        action="member.qr_reissued",
        request=request,
    )
    member_auth.sign_out_everywhere(db, member.id)
    db.commit()
    return member_detail(db, member)


@router.post("/{member_id}/card/reissue", response_model=CardRead)
def reissue_card(
    member_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_EDIT)),
) -> CardRead:
    """A lost card: the old one stops working at once; the app is unaffected."""
    member = load_member(db, ctx, member_id)
    members_service.update(
        db,
        ctx,
        member,
        {"card_token": members_service.new_card_token()},
        action="member.card_reissued",
        request=request,
    )
    db.commit()
    return _card(db, member)


@router.get("/{member_id}/card", response_model=CardRead)
def get_card(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.MEMBERS_EDIT)),
) -> CardRead:
    """For printing the member's card. The code on it is a credential, so it
    takes the same permission as editing the member."""
    return _card(db, load_member(db, ctx, member_id))


def _card(db: Session, member: Member) -> CardRead:
    from app.api.routes.member_app import logo_url

    gym = db.get(Gym, member.gym_id)
    assert gym is not None
    return CardRead(
        member_id=member.id,
        member_code=member.member_code,
        name=member.name,
        photo_url=storage.signed_url(member.photo_key),
        card_code=qr.card_code(member.card_token),
        gym_name=gym.name,
        logo_url=logo_url(gym),
    )
