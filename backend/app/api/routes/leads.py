"""Enquiries (PLAN.md §16.4, 9.1, 9.2)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext
from app.core.errors import not_found
from app.core.permissions import Permission
from app.core.phone import normalize_phone
from app.core.time import today_in_nepal
from app.db.session import get_db
from app.models.lead import Lead
from app.schemas.leads import LeadIn, LeadMatch, LeadRead, LeadReport, LeadUpdate
from app.services import leads as service

router = APIRouter(prefix="/leads", tags=["enquiries"])

LEADS = require(Permission.LEADS_MANAGE)


def reads(db: Session, rows: list[Lead]) -> list[LeadRead]:
    names = service.names(db, rows)
    out = []
    for row in rows:
        read = LeadRead.model_validate(row)
        read.plan_name = names["plan"].get(row.plan_id) if row.plan_id else None
        read.assigned_name = (
            names["staff"].get(row.assigned_to) if row.assigned_to else None
        )
        read.referred_by_name = (
            names["member"].get(row.referred_by_id) if row.referred_by_id else None
        )
        out.append(read)
    return out


def load(db: Session, ctx: StaffContext, lead_id: uuid.UUID) -> Lead:
    lead = db.scalar(service.visible(ctx).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise not_found("No such enquiry.")
    return lead


@router.get("", response_model=list[LeadRead])
def list_leads(
    lead_status: Annotated[
        str | None, Query(alias="status", pattern="^(new|contacted|trial|joined|lost)$")
    ] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    source: Annotated[str | None, Query(max_length=16)] = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> list[LeadRead]:
    """Newest first; the board groups them by status. Joined and lost: the
    last 90 days, so the board stays about who is still to win."""
    stmt = service.visible(ctx)
    if lead_status:
        stmt = stmt.where(Lead.status == lead_status)
    else:
        recent = dt.datetime.now(dt.UTC) - dt.timedelta(days=90)
        stmt = stmt.where(
            or_(
                Lead.status.in_(("new", "contacted", "trial")),
                Lead.updated_at >= recent,
            )
        )
    if source:
        stmt = stmt.where(Lead.source == source)
    if q:
        term = q.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [Lead.name.ilike(f"%{term}%")]
        if len(digits) >= 3:
            conditions.append(Lead.phone.contains(digits[-10:]))
        stmt = stmt.where(or_(*conditions))
    rows = list(db.scalars(stmt.order_by(Lead.created_at.desc()).limit(500)))
    return reads(db, rows)


@router.get("/phone-check", response_model=list[LeadMatch])
def phone_check(
    phone: Annotated[str, Query(max_length=20)],
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> list[LeadMatch]:
    """Already a member, or already asked? A warning, as on Add member."""
    try:
        number = normalize_phone(phone)
    except ValueError:
        return []
    return [LeadMatch(**m) for m in service.matches(db, ctx, number)]


@router.get("/report", response_model=LeadReport)
def lead_report(
    first: Annotated[dt.date | None, Query(alias="from")] = None,
    last: Annotated[dt.date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> LeadReport:
    """By source: enquiries, trials, joined, and the share that joined."""
    last = last or today_in_nepal()
    first = first or last - dt.timedelta(days=29)
    if first > last:
        first, last = last, first
    return LeadReport(**service.report(db, ctx, first, last))


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> LeadRead:
    lead = service.create(db, ctx, payload.model_dump(), request)
    db.commit()
    return reads(db, [lead])[0]


@router.get("/{lead_id}", response_model=LeadRead)
def get_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> LeadRead:
    lead = db.scalar(service.visible(ctx).where(Lead.id == lead_id))
    if lead is None:
        raise not_found("No such enquiry.")
    return reads(db, [lead])[0]


@router.patch("/{lead_id}", response_model=LeadRead)
def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> LeadRead:
    lead = load(db, ctx, lead_id)
    service.update(
        db, ctx, lead, payload.model_dump(exclude_unset=True), request=request
    )
    db.commit()
    return reads(db, [lead])[0]


@router.post("/{lead_id}/trial", response_model=LeadRead)
def trial_visit(
    lead_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(LEADS),
) -> LeadRead:
    """Trial visit today (9.2)."""
    lead = service.trial(db, ctx, load(db, ctx, lead_id), request)
    db.commit()
    return reads(db, [lead])[0]
