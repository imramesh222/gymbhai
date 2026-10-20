"""The shop at the desk (PLAN.md §20.1)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import Strict
from app.schemas.plans import MAX_PAISA

Category = Literal["supplement", "drink", "snack", "merchandise", "other"]
Method = Literal["cash", "esewa", "khalti", "fonepay", "bank"]


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: Category
    price: int
    # Null: not counted.
    stock: int | None
    low_stock: int | None
    code: str | None
    is_active: bool
    sort_order: int


class ProductIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    category: Category = "supplement"
    price: int = Field(ge=0, le=MAX_PAISA)
    # How many are on the shelf now; leave out for a product not counted.
    stock: int | None = Field(default=None, ge=0, le=100_000)
    low_stock: int | None = Field(default=None, ge=0, le=100_000)
    code: str | None = Field(default=None, max_length=64)
    sort_order: int = 0


class ProductUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Category | None = None
    price: int | None = Field(default=None, ge=0, le=MAX_PAISA)
    low_stock: int | None = Field(default=None, ge=0, le=100_000)
    code: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    sort_order: int | None = None
    # Stop counting (False), or start at 0 (True); counts go through /stock.
    track_stock: bool | None = None


class StockIn(Strict):
    """More arrived (restock: how many), or the shelf was counted (count: how
    many are there)."""

    kind: Literal["restock", "count"]
    quantity: int = Field(ge=0, le=100_000)
    note: str | None = Field(default=None, max_length=300)


class StockMoveRead(BaseModel):
    id: uuid.UUID
    change: int
    reason: str
    sale_id: uuid.UUID | None
    note: str | None
    created_by_name: str | None
    created_at: dt.datetime


class SaleLineIn(Strict):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=100)


class SalePaymentIn(Strict):
    method: Method = "cash"
    transaction_ref: str | None = Field(default=None, max_length=64)


class SaleIn(Strict):
    lines: list[SaleLineIn] = Field(min_length=1, max_length=30)
    # A member, or nobody: a walk-in.
    member_id: uuid.UUID | None = None
    # The member's home branch, or the caller's first, unless given.
    branch_id: uuid.UUID | None = None
    discount: int = Field(default=0, ge=0, le=MAX_PAISA)
    payment: SalePaymentIn = SalePaymentIn()
    note: str | None = Field(default=None, max_length=300)


class SaleLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    name: str
    category: str
    unit_price: int
    quantity: int


class SaleRead(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    member_id: uuid.UUID | None
    member_name: str | None
    total: int
    discount: int
    sold_at: dt.datetime
    note: str | None
    created_by_name: str | None
    voided_at: dt.datetime | None
    void_reason: str | None
    lines: list[SaleLineRead]
    payment_id: uuid.UUID | None
    receipt_no: int | None
    method: str | None


class TopProduct(BaseModel):
    name: str
    quantity: int
    amount: int


class SalesMonth(BaseModel):
    """A month of the gym's own calendar, at the caller's branches."""

    month: str
    calendar: str
    first_day: dt.date
    last_day: dt.date
    items: list[SaleRead]
    # Not counting voided sales.
    total: int
    count: int
    by_category: dict[str, int]
    top: list[TopProduct]
