"""Tax invoices for VAT-registered gyms (PLAN.md §20.4).

GET  PUT  /gym/tax          VAT on or off, the PAN, from when
PUT  DELETE /gym/tax/cbms   reporting to IRD's CBMS, with the gym's login
GET  /tax-invoices?month=   the sales book and the sales return book
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.tenancy import StaffContext
from app.core import sealed
from app.core.errors import AppError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.gym import Gym
from app.models.tax import CREDIT_NOTE, INVOICE, GymTax, TaxInvoice
from app.schemas.tax import CbmsIn, TaxBook, TaxSettingsIn, TaxSettingsRead
from app.services import activity, reports
from app.services import shop as shop_service
from app.services import tax as service

router = APIRouter(tags=["tax"])

SETUP = require(Permission.SETUP_GYM)
LISTED = 1000


def _row(db: Session, ctx: StaffContext) -> GymTax:
    row = service.of_gym(db, ctx.gym_id)
    if row is None:
        row = GymTax(gym_id=ctx.gym_id)
        db.add(row)
        db.flush()
    return row


def _read(db: Session, row: GymTax | None) -> TaxSettingsRead:
    read = TaxSettingsRead(available=service.available())
    if row is None:
        return read
    counts = dict(
        db.execute(
            select(TaxInvoice.cbms_status, func.count())
            .where(TaxInvoice.gym_id == row.gym_id)
            .group_by(TaxInvoice.cbms_status)
        ).all()
    )
    read.vat_registered = row.vat_registered
    read.pan = row.pan
    read.starts_on = row.starts_on
    read.cbms_enabled = row.cbms_enabled
    read.cbms_username = row.cbms_username
    read.cbms_error = row.cbms_error
    read.cbms_counts = {k: v for k, v in counts.items() if k != "off"}
    read.invoices = sum(counts.values())
    return read


def _unavailable() -> None:
    if not service.available():
        raise AppError(
            409,
            "tax_unavailable",
            "Tax invoices aren't available yet: GymBhai isn't IRD-certified.",
        )


@router.get("/gym/tax", response_model=TaxSettingsRead)
def get_tax(
    db: Session = Depends(get_db), ctx: StaffContext = Depends(SETUP)
) -> TaxSettingsRead:
    return _read(db, service.of_gym(db, ctx.gym_id))


@router.put("/gym/tax", response_model=TaxSettingsRead)
def set_tax(
    payload: TaxSettingsIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> TaxSettingsRead:
    _unavailable()
    if payload.vat_registered and not (payload.pan and payload.starts_on):
        raise AppError(
            422, "tax_incomplete", "Enter the gym's PAN and the day invoices start."
        )
    row = _row(db, ctx)
    before = {
        "vat_registered": row.vat_registered,
        "pan": row.pan,
        "starts_on": row.starts_on,
    }
    issued = db.scalar(
        select(func.min(TaxInvoice.issued_at)).where(TaxInvoice.gym_id == ctx.gym_id)
    )
    if issued and payload.pan != row.pan and row.pan:
        # The invoices already issued carry it: a new PAN is a new business.
        raise AppError(409, "tax_pan_fixed", "Invoices have been issued with this PAN.")
    row.vat_registered = payload.vat_registered
    row.pan = payload.pan
    row.starts_on = payload.starts_on
    diff = activity.diff(
        before,
        {
            "vat_registered": row.vat_registered,
            "pan": row.pan,
            "starts_on": row.starts_on,
        },
    )
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "tax.updated",
            entity="gym_tax",
            entity_id=row.id,
            changes=diff,
            request=request,
        )
    db.commit()
    return _read(db, row)


@router.put("/gym/tax/cbms", response_model=TaxSettingsRead)
def set_cbms(
    payload: CbmsIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> TaxSettingsRead:
    """Each invoice and credit note to IRD's CBMS as it's issued."""
    _unavailable()
    row = _row(db, ctx)
    row.cbms_enabled = True
    row.cbms_username = payload.username.strip()
    row.cbms_secret = sealed.seal({"password": payload.password}, row.id)
    row.cbms_error = None
    activity.staff_action(
        db,
        ctx.staff,
        "tax.cbms_set",
        entity="gym_tax",
        entity_id=row.id,
        changes={"username": row.cbms_username},
        request=request,
    )
    db.commit()
    return _read(db, row)


@router.delete("/gym/tax/cbms", response_model=TaxSettingsRead)
def remove_cbms(
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SETUP),
) -> TaxSettingsRead:
    row = _row(db, ctx)
    if row.cbms_enabled:
        row.cbms_enabled = False
        row.cbms_secret = None
        activity.staff_action(
            db,
            ctx.staff,
            "tax.cbms_removed",
            entity="gym_tax",
            entity_id=row.id,
            request=request,
        )
    db.commit()
    return _read(db, row)


@router.get("/tax-invoices", response_model=TaxBook)
def book(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
) -> TaxBook:
    """A month of the gym's own calendar: the sales book and the returns."""
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    month = month or reports.current_month(calendar)
    first, last = reports.month_range(month, calendar)
    start, end = shop_service.bounds(first, last)
    rows = list(
        db.scalars(
            select(TaxInvoice)
            .where(
                TaxInvoice.gym_id == ctx.gym_id,
                TaxInvoice.issued_at >= start,
                TaxInvoice.issued_at < end,
            )
            .order_by(TaxInvoice.kind, TaxInvoice.fiscal_year, TaxInvoice.number)
            .limit(LISTED)
        )
    )
    read = service.reads(db, rows)
    invoices = [r for r in read if r.kind == INVOICE]
    returns = [r for r in read if r.kind == CREDIT_NOTE]
    return TaxBook(
        month=month,
        calendar=calendar,
        first_day=first,
        last_day=last,
        invoices=invoices,
        returns=returns,
        sales_total=sum(r.total for r in invoices),
        sales_taxable=sum(r.taxable for r in invoices),
        sales_vat=sum(r.vat for r in invoices),
        returns_total=sum(r.total for r in returns),
        returns_taxable=sum(r.taxable for r in returns),
        returns_vat=sum(r.vat for r in returns),
    )
