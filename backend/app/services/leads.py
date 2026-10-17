"""Enquiries: people who might join, followed through to joining (PLAN.md
§16.4, 9.1, 9.2, 9.6).

new → contacted → trial → joined, or lost (with a reason) at any point.
Joined comes only from Convert, which links the member it made. Every change
is logged with before and after, as for members.
"""

import datetime as dt
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.activity import ACTOR_PUBLIC
from app.models.gym import Branch, Gym
from app.models.lead import (
    LEAD_JOINED,
    LEAD_LOST,
    LEAD_TRIAL,
    OPEN,
    SOURCES,
    Lead,
)
from app.models.member import Member
from app.models.plan import Plan
from app.models.staff import StaffUser
from app.services import activity, live
from app.services import members as members_service

TRACKED = (
    "branch_id",
    "name",
    "phone",
    "email",
    "source",
    "plan_id",
    "status",
    "follow_up_on",
    "lost_reason",
    "assigned_to",
    "trial_on",
    "referred_by_id",
    "member_id",
    "notes",
)


def snapshot(lead: Lead) -> dict[str, Any]:
    return {name: getattr(lead, name) for name in TRACKED}


def visible(ctx: StaffContext) -> Select:
    """This gym's enquiries, at the branches the staff member works at."""
    stmt = select(Lead).where(Lead.gym_id == ctx.gym_id)
    if ctx.branch_ids is not None:
        stmt = stmt.where(Lead.branch_id.in_(ctx.branch_ids))
    return stmt


def _changed(db: Session, lead: Lead) -> None:
    live.publish(db, gym_id=lead.gym_id, kind=live.LEAD, branch_id=lead.branch_id)


def _check_links(db: Session, ctx: StaffContext, values: dict[str, Any]) -> None:
    """Branch, plan, staff and referring member must all be this gym's."""
    if values.get("branch_id") is not None:
        members_service._branch(db, ctx, values["branch_id"])
    if values.get("plan_id") is not None:
        plan = db.get(Plan, values["plan_id"])
        if plan is None or plan.gym_id != ctx.gym_id:
            raise AppError(422, "bad_plan", "That plan does not exist.")
    if values.get("assigned_to") is not None:
        staff = db.get(StaffUser, values["assigned_to"])
        if staff is None or staff.gym_id != ctx.gym_id or not staff.is_active:
            raise AppError(422, "bad_staff", "That staff member does not exist.")
    if values.get("referred_by_id") is not None:
        member = db.get(Member, values["referred_by_id"])
        if member is None or member.gym_id != ctx.gym_id:
            raise AppError(422, "bad_member", "That member does not exist.")


def create(
    db: Session, ctx: StaffContext, values: dict[str, Any], request: Request | None
) -> Lead:
    if values.get("branch_id") is None:
        values["branch_id"] = members_service.default_branch_id(db, ctx)
    _check_links(db, ctx, values)
    lead = Lead(gym_id=ctx.gym_id, created_by=ctx.staff.id, **values)
    if lead.source == "referral" or lead.referred_by_id:
        lead.source = "referral"
    db.add(lead)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "lead.created",
        entity="lead",
        entity_id=lead.id,
        changes=activity.diff({}, snapshot(lead)),
        request=request,
    )
    _changed(db, lead)
    return lead


def update(
    db: Session,
    ctx: StaffContext,
    lead: Lead,
    changes: dict[str, Any],
    *,
    action: str = "lead.updated",
    request: Request | None = None,
) -> Lead:
    if lead.status == LEAD_JOINED and changes.keys() - {"notes"}:
        raise AppError(409, "lead_joined", "They've joined: edit the member instead.")
    _check_links(db, ctx, changes)
    if changes.get("status") == LEAD_LOST and not (
        changes.get("lost_reason") or lead.lost_reason
    ):
        raise AppError(422, "lost_reason_needed", "Say why they didn't join.")
    before = snapshot(lead)
    for name, value in changes.items():
        setattr(lead, name, value)
    if lead.status != LEAD_LOST:
        lead.lost_reason = None
    diff = activity.diff(before, snapshot(lead))
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            action,
            entity="lead",
            entity_id=lead.id,
            changes=diff,
            request=request,
        )
        _changed(db, lead)
    return lead


def trial(
    db: Session, ctx: StaffContext, lead: Lead, request: Request | None = None
) -> Lead:
    """Trial visit today (9.2): not a check-in, as they aren't a member yet."""
    return update(
        db,
        ctx,
        lead,
        {"status": LEAD_TRIAL, "trial_on": today_in_nepal()},
        action="lead.trial",
        request=request,
    )


def convert(
    db: Session,
    ctx: StaffContext,
    lead: Lead,
    member: Member,
    request: Request | None = None,
) -> None:
    """They joined: the new member is linked, and inherits who referred them."""
    if lead.status == LEAD_JOINED:
        raise AppError(409, "lead_joined", "That enquiry has already joined.")
    if member.referred_by_id is None and lead.referred_by_id is not None:
        member.referred_by_id = lead.referred_by_id
    before = snapshot(lead)
    lead.status = LEAD_JOINED
    lead.member_id = member.id
    lead.lost_reason = None
    activity.staff_action(
        db,
        ctx.staff,
        "lead.joined",
        entity="lead",
        entity_id=lead.id,
        changes=activity.diff(before, snapshot(lead)),
        request=request,
    )
    _changed(db, lead)


DUE_SHOWN = 10


def due(db: Session, ctx: StaffContext, today: dt.date) -> tuple[int, list[Lead]]:
    """Open enquiries whose follow-up day has come: for Today."""
    stmt = visible(ctx).where(Lead.status.in_(OPEN), Lead.follow_up_on <= today)
    count = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Lead.follow_up_on, Lead.created_at).limit(DUE_SHOWN)
    ).all()
    return count, list(rows)


def matches(db: Session, ctx: StaffContext, phone: str) -> list[dict[str, Any]]:
    """Members and enquiries already on this number: a warning, not a block."""
    out: list[dict[str, Any]] = [
        {"id": m.id, "name": m.name, "kind": "member", "detail": m.member_code}
        for m in members_service.same_phone(db, ctx.gym_id, phone)
    ]
    for lead in db.scalars(visible(ctx).where(Lead.phone == phone).limit(10)):
        out.append(
            {"id": lead.id, "name": lead.name, "kind": "lead", "detail": lead.status}
        )
    return out


def report(
    db: Session, ctx: StaffContext, first: dt.date, last: dt.date
) -> dict[str, Any]:
    """Enquiries made in [first, last] by source, and how far they got."""
    start = dt.datetime.combine(first, dt.time(), NEPAL)
    end = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), NEPAL)
    stmt = visible(ctx).where(Lead.created_at >= start, Lead.created_at < end)
    sub = stmt.subquery()
    rows = db.execute(
        select(
            sub.c.source,
            func.count(),
            func.count().filter(sub.c.trial_on.is_not(None)),
            func.count().filter(sub.c.status == LEAD_JOINED),
        ).group_by(sub.c.source)
    ).all()
    found = {source: (n, trials, joined) for source, n, trials, joined in rows}

    def row(source: str, n: int, trials: int, joined: int) -> dict[str, Any]:
        return {
            "source": source,
            "enquiries": n,
            "trials": trials,
            "joined": joined,
            "conversion": joined / n if n else None,
        }

    out = [row(s, *found.get(s, (0, 0, 0))) for s in SOURCES]
    totals = [sum(r[k] for r in out) for k in ("enquiries", "trials", "joined")]
    referrers = top_referrers(db, ctx, start, end)
    return {
        "first_day": first,
        "last_day": last,
        "rows": out,
        "total": row("all", *totals),
        "top_referrers": referrers,
    }


def top_referrers(
    db: Session,
    ctx: StaffContext,
    start: dt.datetime,
    end: dt.datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Members who sent the most people in the period (9.6): enquiries they
    referred, and members who joined naming them, without counting one person
    twice (an enquiry that became a member)."""
    referred = (
        select(Lead.referred_by_id.label("by"), Lead.member_id.label("joined"))
        .where(
            Lead.gym_id == ctx.gym_id,
            Lead.referred_by_id.is_not(None),
            Lead.created_at >= start,
            Lead.created_at < end,
        )
        .union_all(
            select(Member.referred_by_id, Member.id).where(
                Member.gym_id == ctx.gym_id,
                Member.referred_by_id.is_not(None),
                Member.created_at >= start,
                Member.created_at < end,
                ~Member.id.in_(
                    select(Lead.member_id).where(
                        Lead.gym_id == ctx.gym_id, Lead.member_id.is_not(None)
                    )
                ),
            )
        )
        .subquery()
    )
    rows = db.execute(
        select(
            Member.id,
            Member.name,
            Member.member_code,
            func.count().label("referred"),
            func.count(referred.c.joined).label("joined"),
        )
        .join(referred, referred.c.by == Member.id)
        .group_by(Member.id, Member.name, Member.member_code)
        .order_by(func.count().desc(), Member.name)
        .limit(limit)
    ).all()
    return [
        {
            "member_id": r.id,
            "name": r.name,
            "member_code": r.member_code,
            "referred": r.referred,
            "joined": r.joined,
        }
        for r in rows
    ]


def names(db: Session, leads: list[Lead]) -> dict[str, dict[uuid.UUID, str]]:
    """Plan, assigned staff and referring member names for a list: three queries."""
    plan_ids = {lead.plan_id for lead in leads if lead.plan_id}
    staff_ids = {lead.assigned_to for lead in leads if lead.assigned_to}
    member_ids = {lead.referred_by_id for lead in leads if lead.referred_by_id}
    return {
        "plan": dict(
            db.execute(select(Plan.id, Plan.name).where(Plan.id.in_(plan_ids))).all()
        )
        if plan_ids
        else {},
        "staff": dict(
            db.execute(
                select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(staff_ids))
            ).all()
        )
        if staff_ids
        else {},
        "member": dict(
            db.execute(
                select(Member.id, Member.name).where(Member.id.in_(member_ids))
            ).all()
        )
        if member_ids
        else {},
    }


# --- the public join form (9.5) -----------------------------------------------------

JOIN_PER_IP_HOUR = 5
JOIN_PER_GYM_DAY = 100


def from_join_form(
    db: Session, gym: Gym, values: dict[str, Any], ip: str | None
) -> None:
    """Someone asked to join, from the gym's QR. Always an enquiry, never a
    member; the same answer whatever happens, so the form can't be used to find
    out who trains here. Rate-limited per IP at this gym (one shared Wi-Fi
    shouldn't stop another gym's form), and per gym per day."""
    now = utcnow()
    if ip:
        recent = db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.gym_id == gym.id,
                Lead.from_ip == ip,
                Lead.created_at >= now - dt.timedelta(hours=1),
            )
        )
        if recent >= JOIN_PER_IP_HOUR:
            raise AppError(429, "too_many", "Too many requests. Try again later.")
    today_count = db.scalar(
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.gym_id == gym.id,
            Lead.from_ip.is_not(None),
            Lead.created_at >= now - dt.timedelta(days=1),
        )
    )
    if today_count >= JOIN_PER_GYM_DAY:
        raise AppError(429, "too_many", "Too many requests. Try again later.")
    plan_id = values.get("plan_id")
    if plan_id is not None:
        plan = db.get(Plan, plan_id)
        if plan is None or plan.gym_id != gym.id or not plan.is_active:
            plan_id = None
    phone = values.get("phone")
    waiting = (
        db.scalar(
            select(Lead).where(
                Lead.gym_id == gym.id, Lead.phone == phone, Lead.status.in_(OPEN)
            )
        )
        if phone
        else None
    )
    message = (values.get("message") or "").strip()
    if waiting is not None:
        # Asked again: the same enquiry, back at the top of today's calls.
        waiting.follow_up_on = today_in_nepal()
        if message:
            waiting.notes = f"{waiting.notes}\n{message}" if waiting.notes else message
        _changed(db, waiting)
        return
    lead = Lead(
        gym_id=gym.id,
        branch_id=values.get("branch_id") or _first_branch(db, gym),
        name=values["name"],
        phone=phone,
        email=values.get("email"),
        source=values.get("source") or "other",
        plan_id=plan_id,
        follow_up_on=today_in_nepal(),
        notes=message or None,
        from_ip=ip,
    )
    db.add(lead)
    db.flush()
    activity.record(
        db,
        gym_id=gym.id,
        actor_type=ACTOR_PUBLIC,
        actor_id=None,
        action="lead.join_form",
        entity="lead",
        entity_id=lead.id,
    )
    _changed(db, lead)


def _first_branch(db: Session, gym: Gym) -> uuid.UUID:
    branch_id = db.scalar(
        select(Branch.id)
        .where(Branch.gym_id == gym.id, Branch.is_active)
        .order_by(Branch.created_at)
        .limit(1)
    )
    if branch_id is None:
        raise AppError(404, "not_found", "Not found.")
    return branch_id
