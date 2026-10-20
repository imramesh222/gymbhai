"""Supplements, drinks and merchandise sold at the desk (PLAN.md §20.1).

A product is what the gym sells, with its price and, if the gym counts it,
how many are left. A sale is one visit to the till: its lines (each product's
name and price copied, as a membership copies its plan's), and one payment for
the lot, an ordinary payment with a receipt number. A sale is never deleted,
only voided with a reason, which puts its stock back.

Stock is a ledger, like message credits: every sale, void, restock and count
is a row in stock_moves, and `products.stock` is kept equal to their sum in
the same transaction (the product row is locked while it changes).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GymOwned, IdMixin, TimestampMixin

# Fixed, so they translate and add up the same way in every gym.
CATEGORIES = ("supplement", "drink", "snack", "merchandise", "other")

# Why stock changed.
MOVE_SALE = "sale"
MOVE_VOID = "void"
MOVE_RESTOCK = "restock"
MOVE_COUNT = "count"  # counted on the shelf: the difference
MOVES = (MOVE_SALE, MOVE_VOID, MOVE_RESTOCK, MOVE_COUNT)


class Product(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price"),
        # A barcode a USB scanner types at the till, once per gym.
        Index(
            "uq_products_gym_code",
            "gym_id",
            "code",
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(16), default="supplement")
    # Paisa, each.
    price: Mapped[int] = mapped_column(Integer)
    # How many are left; null when the gym doesn't count this one.
    stock: Mapped[int | None] = mapped_column(Integer)
    # Warn on the till when stock falls to this; null: never.
    low_stock: Mapped[int | None] = mapped_column(Integer)
    code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )


class ProductSale(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "product_sales"
    __table_args__ = (
        CheckConstraint("total > 0", name="total"),
        CheckConstraint("discount >= 0", name="discount"),
        Index("ix_product_sales_gym_sold_at", "gym_id", "sold_at"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), index=True
    )
    # A member, or nobody: someone walking in for a bottle of water.
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), index=True
    )
    # Paisa: what was paid, after the discount.
    total: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)


class ProductSaleLine(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "product_sale_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"),)

    sale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_sales.id"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), index=True
    )
    # Copied at the sale: changing the product later changes nothing sold.
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(16))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)


class StockMove(IdMixin, TimestampMixin, GymOwned, Base):
    __tablename__ = "stock_moves"
    __table_args__ = (
        Index("ix_stock_moves_product_created", "product_id", "created_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id")
    )
    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(16))
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_sales.id"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
