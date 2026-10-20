"""Tax invoices for VAT-registered gyms (PLAN.md §20.4)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Strict


class TaxSettingsIn(Strict):
    vat_registered: bool
    # Permanent Account Number: 9 digits.
    pan: str | None = Field(default=None, pattern=r"^\d{9}$")
    starts_on: dt.date | None = None


class CbmsIn(Strict):
    """The gym's CBMS login: IRD's taxpayer username and password."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TaxSettingsRead(BaseModel):
    # Off on a server until GymBhai is IRD-certified billing software.
    available: bool
    vat_registered: bool = False
    pan: str | None = None
    starts_on: dt.date | None = None
    cbms_enabled: bool = False
    cbms_username: str | None = None
    cbms_error: str | None = None
    # Bills sent to CBMS, waiting, and refused.
    cbms_counts: dict[str, int] = {}
    invoices: int = 0


class TaxLine(BaseModel):
    description: str
    quantity: int
    # Paisa, before VAT.
    rate: int
    amount: int


class TaxInvoiceRead(BaseModel):
    id: uuid.UUID
    kind: Literal["invoice", "credit_note"]
    fiscal_year: str
    number: int
    payment_id: uuid.UUID
    # A credit note's invoice, by its number.
    ref_number: int | None = None
    ref_fiscal_year: str | None = None
    seller: dict[str, str | None]
    buyer_name: str
    buyer_address: str | None
    buyer_pan: str | None
    lines: list[TaxLine]
    taxable: int
    vat: int
    total: int
    total_in_words: str
    issued_at: dt.datetime
    # The day in BS, as the invoice prints it: 2083.07.03.
    issued_on_bs: str
    reason: str | None
    prints: int
    cbms_status: str


class TaxBook(BaseModel):
    """A month of the sales book (invoices) and the sales return book."""

    month: str
    calendar: str
    first_day: dt.date
    last_day: dt.date
    invoices: list[TaxInvoiceRead]
    returns: list[TaxInvoiceRead]
    # Paisa.
    sales_total: int
    sales_taxable: int
    sales_vat: int
    returns_total: int
    returns_taxable: int
    returns_vat: int
