"""The shop at the desk (PLAN.md §20.1).

GET  /products?include_hidden=      the catalog (Sell or Manage)
POST /products  PATCH /products/{id}   (Manage)
POST /products/{id}/stock           restocked, or counted (Manage)
GET  /products/{id}/stock           its stock's history (Manage)
GET  /sales?month=                  a month's sales and totals (Reports)
POST /sales                         a sale, paid in full (Sell), Idempotency-Key
POST /sales/{id}/void               with a reason (Void payments)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import idempotency
from app.api.deps import require, require_any
from app.api.presenters import staff_names
from app.api.tenancy import StaffContext, get_in_gym
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.gym import Gym
from app.models.member import Member
from app.models.payment import Payment
from app.models.shop import Product, ProductSale
from app.schemas.money import VoidIn
from app.schemas.shop import (
    ProductIn,
    ProductRead,
    ProductUpdate,
    SaleIn,
    SaleLineRead,
    SaleRead,
    SalesMonth,
    StockIn,
    StockMoveRead,
    TopProduct,
)
from app.services import reports
from app.services import shop as service

router = APIRouter(tags=["shop"])

SELL = require(Permission.SHOP_SELL)
MANAGE = require(Permission.SHOP_MANAGE)
LISTED = 300


# Selling and managing both read the catalog.
CATALOG = Depends(require_any(Permission.SHOP_SELL, Permission.SHOP_MANAGE))


def _product(
    db: Session, ctx: StaffContext, product_id: uuid.UUID, *, for_update=False
) -> Product:
    return get_in_gym(
        db, Product, product_id, ctx, message="No such product.", for_update=for_update
    )


@router.get("/products", response_model=list[ProductRead])
def list_products(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    ctx: StaffContext = CATALOG,
) -> list[Product]:
    return service.products(db, ctx.gym_id, hidden=include_hidden)


@router.post(
    "/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED
)
def create_product(
    payload: ProductIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> Product:
    data = payload.model_dump()
    data["code"] = (data.get("code") or "").strip() or None
    product = service.create_product(db, ctx, data, request)
    db.commit()
    return product


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> Product:
    product = _product(db, ctx, product_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes:
        changes["code"] = (changes["code"] or "").strip() or None
    service.update_product(db, ctx, product, changes, request)
    db.commit()
    return product


@router.post("/products/{product_id}/stock", response_model=ProductRead)
def change_stock(
    product_id: uuid.UUID,
    payload: StockIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> Product:
    product = _product(db, ctx, product_id, for_update=True)
    service.change_stock(
        db, ctx, product, payload.kind, payload.quantity, payload.note, request
    )
    db.commit()
    return product


@router.get("/products/{product_id}/stock", response_model=list[StockMoveRead])
def stock_history(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(MANAGE),
) -> list[StockMoveRead]:
    rows = service.moves(db, _product(db, ctx, product_id))
    names = staff_names(db, [row.created_by for row in rows])
    return [
        StockMoveRead(
            id=row.id,
            change=row.change,
            reason=row.reason,
            sale_id=row.sale_id,
            note=row.note,
            created_by_name=names.get(row.created_by) if row.created_by else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


# --- sales --------------------------------------------------------------------


def sale_reads(db: Session, sales: list[ProductSale]) -> list[SaleRead]:
    """Each sale with its lines, its payment and who: a few queries for all."""
    ids = [s.id for s in sales]
    lines = service.lines_for(db, ids)
    payments = (
        {
            p.sale_id: p
            for p in db.scalars(select(Payment).where(Payment.sale_id.in_(ids)))
        }
        if ids
        else {}
    )
    member_ids = {s.member_id for s in sales if s.member_id}
    members = (
        dict(
            db.execute(
                select(Member.id, Member.name).where(Member.id.in_(member_ids))
            ).all()
        )
        if member_ids
        else {}
    )
    names = staff_names(db, [s.created_by for s in sales])
    reads = []
    for sale in sales:
        payment = payments.get(sale.id)
        reads.append(
            SaleRead(
                id=sale.id,
                branch_id=sale.branch_id,
                member_id=sale.member_id,
                member_name=members.get(sale.member_id) if sale.member_id else None,
                total=sale.total,
                discount=sale.discount,
                sold_at=sale.sold_at,
                note=sale.note,
                created_by_name=names.get(sale.created_by) if sale.created_by else None,
                voided_at=sale.voided_at,
                void_reason=sale.void_reason,
                lines=[SaleLineRead.model_validate(line) for line in lines[sale.id]],
                payment_id=payment.id if payment else None,
                receipt_no=payment.receipt_no if payment else None,
                method=payment.method if payment else None,
            )
        )
    return reads


@router.get("/sales", response_model=SalesMonth)
def list_sales(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.REPORTS_MONEY)),
) -> SalesMonth:
    """A month of the gym's own calendar, newest first, with what it adds up to."""
    gym = db.get(Gym, ctx.gym_id)
    assert gym is not None
    calendar = "ad" if gym.config.date_display == "ad" else "bs"
    month = month or reports.current_month(calendar)
    first, last = reports.month_range(month, calendar)
    start, end = service.bounds(first, last)
    sales = list(
        db.scalars(
            service.visible(ctx)
            .where(ProductSale.sold_at >= start, ProductSale.sold_at < end)
            .order_by(ProductSale.sold_at.desc())
            .limit(LISTED)
        )
    )
    total, count, by_category, top = service.month_totals(db, ctx, first, last)
    return SalesMonth(
        month=month,
        calendar=calendar,
        first_day=first,
        last_day=last,
        items=sale_reads(db, sales),
        total=total,
        count=count,
        by_category=by_category,
        top=[TopProduct(name=n, quantity=q, amount=a) for n, q, a in top],
    )


@router.post("/sales", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
def sell(
    payload: SaleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(SELL),
) -> SaleRead:
    """A sale, paid in full: one payment, one receipt. A double tap sells once."""
    idem = idempotency.begin(db, ctx, request, payload)
    sale, _ = service.sell(
        db,
        ctx,
        lines=[(line.product_id, line.quantity) for line in payload.lines],
        member_id=payload.member_id,
        branch_id=payload.branch_id,
        discount=payload.discount,
        method=payload.payment.method,
        transaction_ref=payload.payment.transaction_ref,
        note=payload.note,
        request=request,
    )
    answer = sale_reads(db, [sale])[0]
    idem.finish(answer)
    db.commit()
    return answer


@router.post("/sales/{sale_id}/void", response_model=SaleRead)
def void_sale(
    sale_id: uuid.UUID,
    payload: VoidIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: StaffContext = Depends(require(Permission.PAYMENTS_VOID)),
) -> SaleRead:
    sale = get_in_gym(
        db,
        ProductSale,
        sale_id,
        ctx,
        branch_column=ProductSale.branch_id,
        message="No such sale.",
    )
    service.void(db, ctx, sale, payload.reason, request)
    db.commit()
    return sale_reads(db, [sale])[0]
