"""Selling supplements and the like at the desk (PLAN.md §20.1).

* A sale is paid in full there and then: one ordinary payment, with a receipt
  number, so Today, Payments, Reports and the exports count it like any other
  money in. A walk-in's sale has no member.
* Products are locked (in id order, so two tills can't deadlock) while the
  sale counts their stock: two desks can't both sell the last tub.
* A sale is voided, never deleted, which voids its payment and puts its stock
  back. Voiding is *Void payments*, as for any payment.
* The products and their stock are the whole gym's; the sales, each branch's.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.core.time import NEPAL, utcnow
from app.models.member import Member
from app.models.payment import KIND_PAYMENT, Payment
from app.models.shop import (
    MOVE_COUNT,
    MOVE_RESTOCK,
    MOVE_SALE,
    MOVE_VOID,
    Product,
    ProductSale,
    ProductSaleLine,
    StockMove,
)
from app.services import activity, counters, live, tax
from app.services import members as members_service
from app.services import memberships as ms

PRODUCT_FIELDS = (
    "name",
    "category",
    "price",
    "stock",
    "low_stock",
    "code",
    "is_active",
    "sort_order",
)


def _snapshot(product: Product) -> dict[str, Any]:
    return {name: getattr(product, name) for name in PRODUCT_FIELDS}


def _changed(db: Session, gym_id: uuid.UUID, branch_id: uuid.UUID | None) -> None:
    live.publish(db, gym_id=gym_id, kind=live.SHOP, branch_id=branch_id)


def _code_taken(exc: IntegrityError) -> AppError:
    return AppError(409, "code_taken", "Another product has that barcode.")


# --- products -----------------------------------------------------------------


def products(db: Session, gym_id: uuid.UUID, *, hidden: bool = False) -> list[Product]:
    stmt = select(Product).where(Product.gym_id == gym_id)
    if not hidden:
        stmt = stmt.where(Product.is_active)
    return list(db.scalars(stmt.order_by(Product.sort_order, Product.name)))


def _move(
    db: Session,
    ctx: StaffContext,
    product: Product,
    change: int,
    reason: str,
    *,
    sale_id: uuid.UUID | None = None,
    note: str | None = None,
) -> None:
    db.add(
        StockMove(
            gym_id=product.gym_id,
            product_id=product.id,
            change=change,
            reason=reason,
            sale_id=sale_id,
            note=note,
            created_by=ctx.staff.id,
        )
    )
    product.stock = (product.stock or 0) + change


def create_product(
    db: Session, ctx: StaffContext, data: dict[str, Any], request: Request | None
) -> Product:
    opening = data.pop("stock", None)
    product = Product(gym_id=ctx.gym_id, stock=None, **data)
    db.add(product)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _code_taken(exc) from exc
    if opening is not None:
        product.stock = 0
        _move(db, ctx, product, opening, MOVE_COUNT, note="Opening stock")
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "product.created",
        entity="product",
        entity_id=product.id,
        changes=_snapshot(product),
        request=request,
    )
    _changed(db, ctx.gym_id, None)
    return product


def update_product(
    db: Session,
    ctx: StaffContext,
    product: Product,
    changes: dict[str, Any],
    request: Request | None,
) -> Product:
    before = _snapshot(product)
    track = changes.pop("track_stock", None)
    for name, value in changes.items():
        if value is None and name in ("name", "category", "price", "is_active"):
            continue
        setattr(product, name, value)
    if track is False:
        product.stock = None
    elif track is True and product.stock is None:
        product.stock = 0
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _code_taken(exc) from exc
    diff = activity.diff(before, _snapshot(product))
    if diff:
        activity.staff_action(
            db,
            ctx.staff,
            "product.updated",
            entity="product",
            entity_id=product.id,
            changes=diff,
            request=request,
        )
        _changed(db, ctx.gym_id, None)
    return product


def change_stock(
    db: Session,
    ctx: StaffContext,
    product: Product,
    kind: str,
    quantity: int,
    note: str | None,
    request: Request | None,
) -> Product:
    """More arrived, or the shelf was counted. `product` is locked."""
    if kind == MOVE_RESTOCK:
        if quantity <= 0:
            raise AppError(422, "bad_quantity", "How many arrived?")
        change = quantity
    else:
        change = quantity - (product.stock or 0)
    before = product.stock
    if product.stock is None:
        product.stock = 0  # counting it from now on
    _move(db, ctx, product, change, kind, note=note)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        f"product.{kind}",
        entity="product",
        entity_id=product.id,
        changes={"stock": {"before": before, "after": product.stock}},
        reason=note,
        request=request,
    )
    _changed(db, ctx.gym_id, None)
    return product


def moves(db: Session, product: Product, limit: int = 50) -> list[StockMove]:
    return list(
        db.scalars(
            select(StockMove)
            .where(StockMove.product_id == product.id)
            .order_by(StockMove.created_at.desc(), StockMove.id)
            .limit(limit)
        )
    )


# --- selling ------------------------------------------------------------------


def _lines(db: Session, ctx: StaffContext, wanted: Sequence[tuple[uuid.UUID, int]]):
    """The products, locked in id order, with the quantity of each (a product
    on two lines counts once)."""
    quantity: dict[uuid.UUID, int] = defaultdict(int)
    for product_id, count in wanted:
        quantity[product_id] += count
    rows = {
        p.id: p
        for p in db.scalars(
            select(Product)
            .where(Product.gym_id == ctx.gym_id, Product.id.in_(quantity))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    picked = []
    for product_id, count in quantity.items():
        product = rows.get(product_id)
        if product is None:
            raise AppError(422, "bad_product", "That product does not exist.")
        if not product.is_active:
            raise AppError(422, "product_hidden", f"{product.name} is no longer sold.")
        if product.stock is not None and product.stock < count:
            raise AppError(
                409,
                "out_of_stock",
                f"Only {product.stock} {product.name} left.",
                product=product.name,
                left=product.stock,
            )
        picked.append((product, count))
    return picked


def sell(
    db: Session,
    ctx: StaffContext,
    *,
    lines: Sequence[tuple[uuid.UUID, int]],
    member_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    discount: int,
    method: str,
    transaction_ref: str | None,
    note: str | None,
    request: Request | None = None,
) -> tuple[ProductSale, Payment]:
    member = None
    if member_id is not None:
        member = db.get(Member, member_id)
        if member is None or member.gym_id != ctx.gym_id:
            raise AppError(422, "bad_member", "That member does not exist.")
        members_service.ensure_not_erased(member)
    if branch_id is None:
        branch_id = (
            member.home_branch_id
            if member is not None and ctx.can_access_branch(member.home_branch_id)
            else members_service.default_branch_id(db, ctx)
        )
    branch = ms._branch_in_gym(db, ctx, branch_id)

    picked = _lines(db, ctx, lines)
    subtotal = sum(product.price * count for product, count in picked)
    if discount > subtotal:
        raise AppError(
            422, "bad_discount", "The discount can't be more than the price."
        )
    total = subtotal - discount
    if total <= 0:
        raise AppError(422, "nothing_to_pay", "There is nothing to pay.")

    ref = (transaction_ref or "").strip() or None
    if method == "cash":
        ref = None
    if ref:
        ms.lock_transaction_ref(db, ctx.gym_id, ref)
        if db.scalar(
            select(Payment.id).where(
                Payment.gym_id == ctx.gym_id, Payment.transaction_ref == ref
            )
        ):
            raise AppError(
                409,
                "transaction_ref_used",
                "That transaction ID has already been used.",
            )

    now = utcnow()
    sale = ProductSale(
        id=uuid.uuid4(),
        gym_id=ctx.gym_id,
        branch_id=branch.id,
        member_id=member.id if member else None,
        total=total,
        discount=discount,
        sold_at=now,
        note=note,
        created_by=ctx.staff.id,
    )
    db.add(sale)
    db.flush()
    for product, count in picked:
        db.add(
            ProductSaleLine(
                gym_id=ctx.gym_id,
                sale_id=sale.id,
                product_id=product.id,
                name=product.name,
                category=product.category,
                unit_price=product.price,
                quantity=count,
            )
        )
        if product.stock is not None:
            _move(db, ctx, product, -count, MOVE_SALE, sale_id=sale.id)
    payment = Payment(
        gym_id=ctx.gym_id,
        member_id=sale.member_id,
        sale_id=sale.id,
        kind=KIND_PAYMENT,
        amount=total,
        method=method,
        transaction_ref=ref,
        paid_at=now,
        receipt_no=counters.next_value(db, ctx.gym_id, counters.RECEIPT_NO),
        received_by=ctx.staff.id,
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409, "transaction_ref_used", "That transaction ID has already been used."
        ) from exc
    # A VAT-registered gym's invoice for what was bought (§20.4).
    tax.on_payment(db, payment, ctx.staff.id)
    activity.staff_action(
        db,
        ctx.staff,
        "shop.sold",
        entity="product_sale",
        entity_id=sale.id,
        changes={
            "member_id": sale.member_id,
            "lines": [
                {"product_id": p.id, "name": p.name, "price": p.price, "quantity": n}
                for p, n in picked
            ],
            "discount": discount,
            "total": total,
            "method": method,
            "transaction_ref": ref,
            "receipt_no": payment.receipt_no,
        },
        request=request,
    )
    _changed(db, ctx.gym_id, branch.id)
    if member is not None:
        live.member_changed(db, ctx.gym_id, member.id, member.home_branch_id)
    return sale, payment


def void(
    db: Session,
    ctx: StaffContext,
    sale: ProductSale,
    reason: str,
    request: Request | None = None,
) -> ProductSale:
    """A mistake: the sale and its payment voided, the stock put back."""
    db.refresh(sale, with_for_update=True)
    if sale.voided_at is not None:
        raise AppError(409, "sale_voided", "This sale has already been voided.")
    now = utcnow()
    sale.voided_at = now
    sale.voided_by = ctx.staff.id
    sale.void_reason = reason
    for payment in db.scalars(
        select(Payment).where(Payment.sale_id == sale.id, Payment.voided_at.is_(None))
    ):
        payment.voided_at = now
        payment.voided_by = ctx.staff.id
        payment.void_reason = reason
        tax.on_void(db, payment, reason, ctx.staff.id)
    sold = {
        line.product_id: line.quantity
        for line in db.scalars(
            select(ProductSaleLine).where(ProductSaleLine.sale_id == sale.id)
        )
    }
    for product in db.scalars(
        select(Product)
        .where(Product.id.in_(sold))
        .order_by(Product.id)
        .with_for_update()
    ):
        if product.stock is not None:
            _move(db, ctx, product, sold[product.id], MOVE_VOID, sale_id=sale.id)
    db.flush()
    activity.staff_action(
        db,
        ctx.staff,
        "shop.voided",
        entity="product_sale",
        entity_id=sale.id,
        changes={"total": sale.total},
        reason=reason,
        request=request,
    )
    _changed(db, sale.gym_id, sale.branch_id)
    if sale.member_id is not None:
        live.member_changed(db, sale.gym_id, sale.member_id, sale.branch_id)
    return sale


# --- reading ------------------------------------------------------------------


def visible(ctx: StaffContext) -> Select[tuple[ProductSale]]:
    """Sales at the branches the caller works at."""
    stmt = select(ProductSale).where(ProductSale.gym_id == ctx.gym_id)
    if ctx.branch_ids is not None:
        stmt = stmt.where(ProductSale.branch_id.in_(ctx.branch_ids))
    return stmt


def bounds(first: dt.date, last: dt.date) -> tuple[dt.datetime, dt.datetime]:
    return (
        dt.datetime.combine(first, dt.time(), NEPAL),
        dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), NEPAL),
    )


def lines_for(
    db: Session, sale_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[ProductSaleLine]]:
    ids = list(sale_ids)
    found: dict[uuid.UUID, list[ProductSaleLine]] = defaultdict(list)
    if not ids:
        return found
    # By name: a sale's lines are written together, so their times tie.
    for line in db.scalars(
        select(ProductSaleLine)
        .where(ProductSaleLine.sale_id.in_(ids))
        .order_by(ProductSaleLine.name, ProductSaleLine.id)
    ):
        found[line.sale_id].append(line)
    return found


def month_totals(
    db: Session,
    ctx: StaffContext,
    first: dt.date,
    last: dt.date,
    branch_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[int, int, dict[str, int], list[tuple[str, int, int]]]:
    """(money in, sales, money by category, the products sold most) for the
    month, at those branches (the caller's unless given)."""
    start, end = bounds(first, last)
    sales = select(ProductSale.id).where(
        ProductSale.gym_id == ctx.gym_id,
        ProductSale.voided_at.is_(None),
        ProductSale.sold_at >= start,
        ProductSale.sold_at < end,
    )
    branches = branch_ids if branch_ids is not None else ctx.branch_ids
    if branches is not None:
        sales = sales.where(ProductSale.branch_id.in_(list(branches)))
    total, count = db.execute(
        select(func.coalesce(func.sum(ProductSale.total), 0), func.count()).where(
            ProductSale.id.in_(sales)
        )
    ).one()
    gross = ProductSaleLine.unit_price * ProductSaleLine.quantity
    by_category = dict(
        db.execute(
            select(ProductSaleLine.category, func.sum(gross))
            .where(ProductSaleLine.sale_id.in_(sales))
            .group_by(ProductSaleLine.category)
        ).all()
    )
    top = [
        (name, int(quantity), int(amount))
        for name, quantity, amount in db.execute(
            select(
                ProductSaleLine.name,
                func.sum(ProductSaleLine.quantity),
                func.sum(gross),
            )
            .where(ProductSaleLine.sale_id.in_(sales))
            .group_by(ProductSaleLine.name)
            .order_by(func.sum(gross).desc(), ProductSaleLine.name)
            .limit(5)
        ).all()
    ]
    return int(total), int(count), by_category, top
