"""Members: creating them, and where each one stands today.

A member's state is derived from their memberships, never stored:

* active   — a membership covers today and it is not frozen today
* frozen   — a membership covers today and a freeze covers today
* upcoming — nothing covers today, but a membership starts later
* expired  — every membership has ended
* none     — never had one

"Valid until" follows back-to-back renewals: renewing early queues the new
membership the day after the current one ends, and the member's days left run
to the end of the chain.
"""

import datetime as dt
import secrets
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from sqlalchemy import Select, and_, case, delete, exists, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.core.gym_settings import GymSettings
from app.core.phone import normalize_phone
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.activity import ActivityLog
from app.models.gym import Branch
from app.models.lead import Lead
from app.models.member import Member
from app.models.member_app import (
    LET_IN,
    CheckIn,
    MemberSession,
    MemberSignInLink,
    OtpCode,
    PaymentRequest,
)
from app.models.membership import Membership, MembershipFreeze
from app.models.messaging import SmsMessage
from app.models.payment import KIND_PAYMENT, Payment
from app.models.platform import MemberImport
from app.models.progress import ProgressEntry, ProgressPhoto
from app.models.push import PushSubscription
from app.models.training import PtPackage, PtSession
from app.services import activity, counters, live
from app.services import memberships as ms

NONE = "none"
STATUSES = (ms.ACTIVE, ms.FROZEN, ms.UPCOMING, ms.EXPIRED, NONE)

# Fields shown in the History of a member (§5.6).
TRACKED = (
    "name",
    "phone",
    "email",
    "gender",
    "date_of_birth",
    "address",
    "emergency_contact",
    "home_branch_id",
    "referred_by_id",
    "joined_on",
    "notes",
    "app_access",
    "is_archived",
    "photo_key",
    "qr_version",
    "card_token",
    "language",
)


def new_qr_secret() -> str:
    return secrets.token_hex(32)


def new_card_token() -> str:
    return secrets.token_urlsafe(18)


def snapshot(member: Member) -> dict[str, Any]:
    return {name: getattr(member, name) for name in TRACKED}


def _branch(db: Session, ctx: StaffContext, branch_id: uuid.UUID) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or branch.gym_id != ctx.gym_id:
        raise AppError(422, "bad_branch", "That branch does not exist.")
    if not ctx.can_access_branch(branch.id):
        raise AppError(403, "branch_denied", "You don't work at that branch.")
    return branch


def _referrer(db: Session, ctx: StaffContext, member_id: uuid.UUID) -> Member:
    member = db.get(Member, member_id)
    if member is None or member.gym_id != ctx.gym_id:
        raise AppError(422, "bad_member", "That member does not exist.")
    return member


def default_branch_id(db: Session, ctx: StaffContext) -> uuid.UUID:
    stmt = select(Branch.id).where(Branch.gym_id == ctx.gym_id, Branch.is_active)
    if ctx.branch_ids is not None:
        stmt = stmt.where(Branch.id.in_(ctx.branch_ids))
    branch_id = db.scalar(stmt.order_by(Branch.created_at).limit(1))
    if branch_id is None:
        raise AppError(422, "no_branch", "Add a branch first.")
    return branch_id


def create(
    db: Session,
    ctx: StaffContext,
    data: dict[str, Any],
    config: GymSettings,
    *,
    request: Request | None = None,
) -> Member:
    return create_many(db, ctx, [data], config, request=request)[0]


def create_many(
    db: Session,
    ctx: StaffContext,
    rows: Sequence[dict[str, Any]],
    config: GymSettings,
    *,
    request: Request | None = None,
) -> list[Member]:
    """Members added together, each logged as if added at the desk.

    One counter update and one batched insert however many there are: an
    imported register of thousands would otherwise make several round trips
    to the database per member.
    """
    if not rows:
        return []
    rows = [dict(data) for data in rows]
    default: uuid.UUID | None = None
    checked: set[uuid.UUID] = set()
    for data in rows:
        if data.get("home_branch_id") is None:
            default = default or default_branch_id(db, ctx)
            data["home_branch_id"] = default
        if data.get("referred_by_id") is not None:
            _referrer(db, ctx, data["referred_by_id"])
        if data["home_branch_id"] not in checked:
            _branch(db, ctx, data["home_branch_id"])
            checked.add(data["home_branch_id"])

    today = today_in_nepal()
    numbers = counters.next_values(db, ctx.gym_id, counters.MEMBER_CODE, len(rows))
    members = [
        Member(
            id=uuid.uuid4(),
            gym_id=ctx.gym_id,
            member_code=f"{config.member_code_prefix}-{number:04d}",
            joined_on=data.pop("joined_on", None) or today,
            qr_secret=new_qr_secret(),
            card_token=new_card_token(),
            **data,
        )
        for data, number in zip(rows, numbers, strict=True)
    ]
    db.add_all(members)
    db.flush()
    for member in members:
        activity.staff_action(
            db,
            ctx.staff,
            "member.created",
            entity="member",
            entity_id=member.id,
            changes={"member_code": member.member_code, **snapshot(member)},
            request=request,
        )
    return members


def update(
    db: Session,
    ctx: StaffContext,
    member: Member,
    changes: dict[str, Any],
    *,
    action: str = "member.updated",
    reason: str | None = None,
    request: Request | None = None,
) -> Member:
    ensure_not_erased(member)
    if changes.get("home_branch_id") is not None:
        _branch(db, ctx, changes["home_branch_id"])
    if changes.get("referred_by_id") is not None:
        if changes["referred_by_id"] == member.id:
            raise AppError(422, "bad_member", "A member can't refer themselves.")
        _referrer(db, ctx, changes["referred_by_id"])
    before = snapshot(member)
    for name, value in changes.items():
        setattr(member, name, value)
    if member.phone != before["phone"] or member.email != before["email"]:
        # The old phone or email stops working at once, and devices sign out.
        from app.services.member_auth import sign_out_everywhere

        sign_out_everywhere(db, member.id)
    diff = activity.diff(before, snapshot(member))
    if diff:
        live.member_changed(db, ctx.gym_id, member.id, member.home_branch_id)
        activity.staff_action(
            db,
            ctx.staff,
            action,
            entity="member",
            entity_id=member.id,
            changes=diff,
            reason=reason,
            request=request,
        )
    return member


# What a member may change in their own app (PLAN.md §16.3, 8.5). The email
# comes through member_auth.confirm_email_change; never the phone, which is
# how the gym knows them and signs them in.
SELF_EDITABLE = ("email", "emergency_contact", "photo_key", "language")


def update_by_member(
    db: Session,
    member: Member,
    changes: dict[str, Any],
    *,
    action: str = "member.updated_own",
    request: Request | None = None,
) -> Member:
    """The member's own change, logged with them as the one who made it."""
    ensure_not_erased(member)
    unknown = set(changes) - set(SELF_EDITABLE)
    if unknown:
        raise ValueError(f"Members can't change {sorted(unknown)}")
    before = snapshot(member)
    for name, value in changes.items():
        setattr(member, name, value)
    diff = activity.diff(before, snapshot(member))
    if diff:
        live.member_changed(db, member.gym_id, member.id, member.home_branch_id)
        activity.member_action(db, member, action, changes=diff, request=request)
    return member


def same_phone(
    db: Session, gym_id: uuid.UUID, phone: str, exclude: uuid.UUID | None = None
) -> list[Member]:
    """Members already on file with this phone: families often share one (§5.5)."""
    stmt = select(Member).where(
        Member.gym_id == gym_id, Member.phone == phone, Member.is_archived.is_(False)
    )
    if exclude is not None:
        stmt = stmt.where(Member.id != exclude)
    return list(db.scalars(stmt.order_by(Member.name)))


# --- where a member stands ------------------------------------------------------


@dataclass
class MemberState:
    status: str
    current: Membership | None = None
    valid_until: dt.date | None = None
    days_left: int = 0
    dues: int = 0
    memberships: list[Membership] = field(default_factory=list)
    # A visit pack (§16.4, 9.3): used and allowed on `current`.
    visits_used: int | None = None
    visit_limit: int | None = None
    # Its dates cover today, but every visit is used: the door says so.
    used_up_today: bool = False
    # Owed by whoever pays for a family or couple plan they're on (§19.1):
    # not in `dues`, which is theirs to pay, but the door's dues rule counts it.
    group_dues: int = 0

    @property
    def visits_left(self) -> int | None:
        if self.visit_limit is None or self.visits_used is None:
            return None
        return max(self.visit_limit - self.visits_used, 0)


def state_of(
    memberships: Sequence[Membership],
    freezes: dict[uuid.UUID, list[MembershipFreeze]],
    payments: dict[uuid.UUID, list[Payment]],
    today: dt.date | None = None,
    visits: dict[uuid.UUID, int] | None = None,
) -> MemberState:
    """Computed from dates, and for visit packs the visits used (§16.4, 9.3):
    a pack with every visit used counts as ended."""
    today = today or today_in_nepal()
    visits = visits or {}

    def used_up(m: Membership) -> bool:
        return m.visit_limit is not None and visits.get(m.id, 0) >= m.visit_limit

    all_live = sorted(
        (m for m in memberships if m.cancelled_at is None), key=lambda m: m.start_date
    )
    live = [m for m in all_live if not used_up(m)]
    dues = sum(ms.dues_of(m, payments.get(m.id, [])) for m in memberships)

    def chain_end(first: Membership) -> dt.date:
        end = first.end_date
        for m in live:
            if m.start_date <= end + dt.timedelta(days=1) and m.end_date > end:
                end = m.end_date
        return end

    covering = [m for m in live if m.start_date <= today <= m.end_date]
    if covering:
        current = covering[-1]
        frozen = any(
            f.from_date <= today <= f.to_date for f in freezes.get(current.id, [])
        )
        until = chain_end(covering[0])
        return MemberState(
            status=ms.FROZEN if frozen else ms.ACTIVE,
            current=current,
            valid_until=until,
            days_left=(until - today).days + 1,
            dues=dues,
            memberships=list(memberships),
            visits_used=visits.get(current.id, 0) if current.visit_limit else None,
            visit_limit=current.visit_limit,
        )
    upcoming = [m for m in live if m.start_date > today]
    if upcoming:
        return MemberState(
            status=ms.UPCOMING,
            current=upcoming[0],
            valid_until=chain_end(upcoming[0]),
            dues=dues,
            memberships=list(memberships),
        )
    spent = [m for m in all_live if used_up(m) and m.start_date <= today <= m.end_date]
    if all_live:
        last = spent[-1] if spent else max(all_live, key=lambda m: m.end_date)
        return MemberState(
            status=ms.EXPIRED,
            current=last,
            valid_until=last.end_date,
            dues=dues,
            memberships=list(memberships),
            visits_used=visits.get(last.id, 0) if last.visit_limit else None,
            visit_limit=last.visit_limit,
            used_up_today=bool(spent),
        )
    return MemberState(status=NONE, dues=dues, memberships=list(memberships))


@dataclass
class StateInputs:
    """Everything members' states are computed from, loaded once: any day's
    state comes from it with no more queries (the kiosk's roster, §19.2)."""

    by_member: dict[uuid.UUID, list[Membership]]
    freezes: dict[uuid.UUID, list[MembershipFreeze]]
    payments: dict[uuid.UUID, list[Payment]]
    visits: dict[uuid.UUID, int]
    group_dues: dict[uuid.UUID, int]

    def state(self, member_id: uuid.UUID, today: dt.date | None = None) -> MemberState:
        found = state_of(
            self.by_member.get(member_id, []),
            self.freezes,
            self.payments,
            today,
            self.visits,
        )
        found.group_dues = self.group_dues.get(member_id, 0)
        return found


def state_inputs(db: Session, members: Sequence[Member]) -> StateInputs:
    """In four queries, however many members (five with a family plan)."""
    ids = [m.id for m in members]
    rows = (
        list(db.scalars(select(Membership).where(Membership.member_id.in_(ids))))
        if ids
        else []
    )
    by_member: dict[uuid.UUID, list[Membership]] = defaultdict(list)
    for row in rows:
        by_member[row.member_id].append(row)
    membership_ids = [r.id for r in rows]
    freezes: dict[uuid.UUID, list[MembershipFreeze]] = defaultdict(list)
    for f in ms.freezes_for(db, membership_ids):
        freezes[f.membership_id].append(f)
    payments: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for p in ms.payments_for(db, membership_ids):
        payments[p.membership_id].append(p)  # type: ignore[index]
    return StateInputs(
        by_member=by_member,
        freezes=freezes,
        payments=payments,
        visits=ms.visits_used(db, rows),
        group_dues=ms.group_dues_for(db, rows),
    )


def states_for(
    db: Session, members: Sequence[Member], today: dt.date | None = None
) -> dict[uuid.UUID, MemberState]:
    """Every member's state in three queries, however many members."""
    if not members:
        return {}
    inputs = state_inputs(db, members)
    return {m.id: inputs.state(m.id, today) for m in members}


def state(db: Session, member: Member) -> MemberState:
    return states_for(db, [member])[member.id]


# --- search and filters (SQL) ---------------------------------------------------


def _covering_today(today: dt.date):
    return and_(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.start_date <= today,
        Membership.end_date >= today,
        ms.usable(),
    )


def _frozen_today(today: dt.date):
    return exists().where(
        MembershipFreeze.membership_id == Membership.id,
        MembershipFreeze.from_date <= today,
        MembershipFreeze.to_date >= today,
    )


def status_filter(status: str, today: dt.date):
    covering = exists().where(_covering_today(today))
    covering_frozen = exists().where(_covering_today(today), _frozen_today(today))
    covering_open = exists().where(_covering_today(today), ~_frozen_today(today))
    future = exists().where(
        Membership.member_id == Member.id,
        Membership.cancelled_at.is_(None),
        Membership.start_date > today,
    )
    any_live = exists().where(
        Membership.member_id == Member.id, Membership.cancelled_at.is_(None)
    )
    if status == ms.ACTIVE:
        return covering_open
    if status == ms.FROZEN:
        return covering_frozen
    if status == ms.UPCOMING:
        return and_(~covering, future)
    if status == ms.EXPIRED:
        return and_(any_live, ~covering, ~future)
    if status == NONE:
        return ~any_live
    raise AppError(422, "bad_status", "Unknown status.")


def dues_expression():
    """Per-member dues, as a correlated SQL expression (see memberships.dues_of)."""
    owed = (
        select(
            func.coalesce(
                func.sum(
                    Membership.price - Membership.discount + Membership.admission_fee
                ),
                0,
            )
        )
        .where(Membership.member_id == Member.id, Membership.cancelled_at.is_(None))
        .scalar_subquery()
    )
    live_membership = exists().where(
        Membership.id == Payment.membership_id, Membership.cancelled_at.is_(None)
    )
    paid = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Payment.kind == KIND_PAYMENT, Payment.amount),
                        else_=-Payment.amount,
                    )
                ),
                0,
            )
        )
        .where(
            Payment.member_id == Member.id,
            Payment.voided_at.is_(None),
            live_membership,
        )
        .scalar_subquery()
    )
    return owed - paid


def last_visit_expression():
    """When a member was last let in at the door, for sorting (null: never)."""
    return (
        select(func.max(CheckIn.at))
        .where(CheckIn.member_id == Member.id, CheckIn.result.in_(LET_IN))
        .correlate(Member)
        .scalar_subquery()
    )


def last_visits(db: Session, member_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    """Each member's last visit, in one query for the whole page."""
    if not member_ids:
        return {}
    return dict(
        db.execute(
            select(CheckIn.member_id, func.max(CheckIn.at))
            .where(CheckIn.member_id.in_(member_ids), CheckIn.result.in_(LET_IN))
            .group_by(CheckIn.member_id)
        ).all()
    )


def expiring_filter(today: dt.date, within_days: int):
    """Active now, and the last day of their chain falls within N days."""
    last_end = (
        select(func.max(Membership.end_date))
        .where(Membership.member_id == Member.id, Membership.cancelled_at.is_(None))
        .scalar_subquery()
    )
    return and_(
        exists().where(_covering_today(today)),
        last_end <= today + dt.timedelta(days=within_days),
    )


def not_visiting_filter(today: dt.date, days: int):
    """Active today (not frozen), and not let in at the door for N days.

    Someone who joined in the last N days hasn't had the chance yet: left out.
    """
    since = dt.datetime.combine(today - dt.timedelta(days=days), dt.time(), NEPAL)
    visited = exists().where(
        CheckIn.member_id == Member.id,
        CheckIn.result.in_(LET_IN),
        CheckIn.at >= since,
    )
    return and_(status_filter(ms.ACTIVE, today), ~visited, Member.created_at < since)


def search(
    ctx: StaffContext,
    *,
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    has_dues: bool | None = None,
    expiring_within: int | None = None,
    not_visiting_days: int | None = None,
    archived: bool = False,
    today: dt.date | None = None,
) -> Select:
    today = today or today_in_nepal()
    stmt = select(Member).where(
        Member.gym_id == ctx.gym_id, Member.is_archived.is_(archived)
    )
    if ctx.branch_ids is not None:
        stmt = stmt.where(Member.home_branch_id.in_(ctx.branch_ids))
    if q:
        term = q.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [
            Member.name.ilike(f"%{term}%"),
            Member.member_code.ilike(f"%{term}%"),
        ]
        if len(digits) >= 3:
            conditions.append(Member.phone.contains(digits[-10:]))
        stmt = stmt.where(or_(*conditions))
    if status:
        stmt = stmt.where(status_filter(status, today))
    if branch_id:
        stmt = stmt.where(Member.home_branch_id == branch_id)
    if plan_id:
        stmt = stmt.where(
            exists().where(_covering_today(today), Membership.plan_id == plan_id)
        )
    if has_dues is not None:
        dues = dues_expression()
        stmt = stmt.where(dues > 0 if has_dues else dues <= 0)
    if expiring_within is not None:
        stmt = stmt.where(expiring_filter(today, expiring_within))
    if not_visiting_days is not None:
        stmt = stmt.where(not_visiting_filter(today, not_visiting_days))
    return stmt


# --- erasing (PLAN.md §16.1) ---------------------------------------------------------

ERASED_NAME = "Erased member"
# Phone is required. No Nepali mobile number starts with 0: this reaches nobody.
ERASED_PHONE = "0000000000"
ERASED_SMS = "(erased)"


def ensure_not_erased(member: Member) -> None:
    if member.erased_at is not None:
        raise AppError(409, "member_erased", "This member's details were erased.")


def _shared(db: Session, member: Member, column, value: str | None) -> bool:
    """Someone else at this gym still uses that phone or email (a family)."""
    if not value:
        return False
    return bool(
        db.scalar(
            select(Member.id).where(
                Member.gym_id == member.gym_id,
                Member.id != member.id,
                Member.erased_at.is_(None),
                column == value,
            )
        )
    )


def _has_phone(values: list[Any], phone: str) -> bool:
    for value in values:
        try:
            if value is not None and normalize_phone(str(value)) == phone:
                return True
        except ValueError:
            continue
    return False


def erase(
    db: Session, ctx: StaffContext, member: Member, request: Request | None = None
) -> list[str]:
    """Erase a member's personal details, at their request, for good.

    Their name, phone, email, birthday, address, emergency contact, notes and
    photo go, here and on the enquiry they joined from; so do their sign-in
    codes and app sessions, the SMS sent to them, their payment screenshots,
    the notes on their personal training sessions, the before-and-after
    values in their History, and their row in any register imported. Their
    memberships, personal training, payments and check-ins stay, as "Erased
    member": they are the gym's accounts. Returns the stored files to delete
    once this is committed.
    """
    ensure_not_erased(member)
    phone, email = member.phone, member.email
    files = [key for key in [member.photo_key] if key]
    phone_shared = _shared(db, member, Member.phone, phone)
    email_shared = _shared(db, member, func.lower(Member.email), (email or "").lower())

    for name in (
        "email",
        "gender",
        "date_of_birth",
        "address",
        "emergency_contact",
        "notes",
        "photo_key",
    ):
        setattr(member, name, None)
    member.name = ERASED_NAME
    member.phone = ERASED_PHONE
    member.app_access = False
    member.is_archived = True
    # The app QR and the printed card stop working.
    member.qr_version += 1
    member.qr_secret = new_qr_secret()
    member.card_token = new_card_token()
    member.erased_at = utcnow()

    # Deleted, not just revoked: the device details are theirs too.
    db.execute(delete(MemberSession).where(MemberSession.member_id == member.id))
    db.execute(delete(MemberSignInLink).where(MemberSignInLink.member_id == member.id))
    # A push endpoint names their phone: gone as well.
    db.execute(delete(PushSubscription).where(PushSubscription.member_id == member.id))
    db.execute(
        sql_update(SmsMessage)
        .where(SmsMessage.gym_id == member.gym_id, SmsMessage.member_id == member.id)
        .values(to=ERASED_PHONE, body=ERASED_SMS)
    )
    if not phone_shared:
        db.execute(
            delete(OtpCode).where(
                OtpCode.gym_id == member.gym_id, OtpCode.destination == phone
            )
        )
        # Sign-in codes are logged against the number, not the member.
        db.execute(
            sql_update(SmsMessage)
            .where(SmsMessage.gym_id == member.gym_id, SmsMessage.to == phone)
            .values(to=ERASED_PHONE)
        )
    if email and not email_shared:
        db.execute(
            delete(OtpCode).where(
                OtpCode.gym_id == member.gym_id,
                OtpCode.destination == email.lower(),
            )
        )
    for row in db.scalars(
        select(PaymentRequest).where(
            PaymentRequest.member_id == member.id,
            PaymentRequest.screenshot_key.is_not(None),
        )
    ):
        files.append(row.screenshot_key)  # type: ignore[arg-type]
        row.screenshot_key = None
    # The enquiry they joined from held the same details (§16.4, 9.1).
    lead_ids = list(
        db.scalars(
            select(Lead.id).where(
                Lead.gym_id == member.gym_id, Lead.member_id == member.id
            )
        )
    )
    if lead_ids:
        db.execute(
            sql_update(Lead)
            .where(Lead.id.in_(lead_ids))
            .values(name=ERASED_NAME, phone=None, email=None, notes=None)
        )
    # Their weight, measurements and photos are theirs alone (§19.5).
    files += list(
        db.scalars(
            select(ProgressPhoto.photo_key).where(ProgressPhoto.member_id == member.id)
        )
    )
    db.execute(delete(ProgressPhoto).where(ProgressPhoto.member_id == member.id))
    db.execute(delete(ProgressEntry).where(ProgressEntry.member_id == member.id))
    member.height_mm = None
    # A trainer's notes on their sessions are about them too (§18.3).
    db.execute(
        sql_update(PtSession)
        .where(
            PtSession.gym_id == member.gym_id,
            PtSession.package_id.in_(
                select(PtPackage.id).where(PtPackage.member_id == member.id)
            ),
        )
        .values(note=None)
    )
    # The History keeps what happened and when, not what the details were.
    db.execute(
        sql_update(ActivityLog)
        .where(
            ActivityLog.gym_id == member.gym_id,
            or_(
                and_(
                    ActivityLog.entity == "member", ActivityLog.entity_id == member.id
                ),
                and_(ActivityLog.entity == "lead", ActivityLog.entity_id.in_(lead_ids)),
            ),
        )
        .values(changes=None)
    )
    if not phone_shared:
        for upload in db.scalars(
            select(MemberImport).where(MemberImport.gym_id == member.gym_id)
        ):
            kept = [row for row in upload.rows if not _has_phone(row, phone)]
            if len(kept) != len(upload.rows):
                upload.rows = kept

    activity.staff_action(
        db,
        ctx.staff,
        "member.erased",
        entity="member",
        entity_id=member.id,
        request=request,
    )
    live.member_changed(db, ctx.gym_id, member.id, member.home_branch_id)
    return files
