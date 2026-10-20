import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auth import Strict
from app.schemas.tax import TaxInvoiceRead

Method = Literal["cash", "esewa", "khalti", "fonepay", "bank"]
AccountKind = Literal["esewa", "khalti", "fonepay", "bank", "other"]


class PaymentIn(Strict):
    amount: int = Field(gt=0, le=10_000_000_00)
    method: Method
    transaction_ref: str | None = Field(default=None, max_length=64)
    paid_at: dt.datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class PaymentCollect(PaymentIn):
    """Towards a membership, or towards personal training (§18.3): one of them."""

    membership_id: uuid.UUID | None = None
    pt_package_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_purpose(self) -> "PaymentCollect":
        if (self.membership_id is None) == (self.pt_package_id is None):
            raise ValueError("Give a membership or personal training, not both.")
        return self


class RefundCollect(PaymentCollect):
    pass


class PaymentUpdate(Strict):
    amount: int | None = Field(default=None, gt=0, le=10_000_000_00)
    method: Method | None = None
    transaction_ref: str | None = Field(default=None, max_length=64)
    paid_at: dt.datetime | None = None
    note: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=500)


class VoidIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Null for a walk-in's purchase at the desk (§20.1).
    member_id: uuid.UUID | None
    membership_id: uuid.UUID | None
    pt_package_id: uuid.UUID | None = None
    sale_id: uuid.UUID | None = None
    kind: str
    amount: int
    method: str
    transaction_ref: str | None
    paid_at: dt.datetime
    receipt_no: int
    received_by: uuid.UUID | None
    received_by_name: str | None = None
    note: str | None
    voided_at: dt.datetime | None
    void_reason: str | None


class PaymentListItem(PaymentRead):
    member_name: str | None
    member_code: str | None


class PaymentList(BaseModel):
    items: list[PaymentListItem]
    total: int
    # Net of refunds, excluding voided payments, over the whole filter.
    sum_amount: int
    by_method: dict[str, int]


class Receipt(BaseModel):
    payment: PaymentRead
    gym_name: str
    gym_phone: str | None
    gym_address: str | None
    branch_name: str | None
    # None for a walk-in's purchase at the desk (§20.1).
    member_name: str | None
    member_code: str | None
    member_phone: str | None
    plan_name: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    membership_total: int | None
    dues_after: int | None
    date_display: str
    # For personal training (§18.3): the dates are its, not a membership's.
    training: bool = False
    # What was bought at the desk (§20.1): each line, and any discount.
    items: list["ReceiptItem"] = []
    discount: int = 0
    # A family or couple plan (§19.1): the others it covers, by name.
    covers: list[str] = []
    # It can go to the member on WhatsApp from the desk (§19.3).
    whatsapp: bool = False
    # A VAT-registered gym's tax invoice for it, and any credit note (§20.4).
    tax_documents: list[TaxInvoiceRead] = []


class ReceiptItem(BaseModel):
    name: str
    quantity: int
    unit_price: int


class ReceiptLink(BaseModel):
    """The receipt as a PDF anyone with the link can open, for a while (8.4)."""

    url: str
    filename: str
    # What goes with it when shared: "Fitness Zone: Payment receipt #42, Rs 1,500".
    text: str
    expires_at: dt.datetime


class GatewayStatus(BaseModel):
    """A merchant account's keys, as staff see them: never the keys (§20.2)."""

    merchant: str | None
    # The secret key's last four characters.
    hint: str | None
    test: bool
    ok_at: dt.datetime | None
    error: str | None


class PaymentMethodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    label: str
    account_name: str | None
    account_number: str | None
    qr_image_url: str | None = None
    is_active: bool
    sort_order: int
    # Payments to it are confirmed by the wallet itself (§20.2).
    online: bool = False
    # Staff only; members never see it.
    gateway: GatewayStatus | None = None


class GatewayIn(Strict):
    """The keys the wallet gave the gym: eSewa's merchant code and secret key;
    Khalti's live secret key; Fonepay's merchant code, secret key, username
    and password."""

    merchant: str | None = Field(default=None, max_length=64)
    secret_key: str = Field(min_length=4, max_length=200)
    username: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=200)
    # The wallet's test system.
    test: bool = False


class PaymentMethodCreate(Strict):
    kind: AccountKind
    label: str = Field(min_length=1, max_length=80)
    account_name: str | None = Field(default=None, max_length=120)
    account_number: str | None = Field(default=None, max_length=64)
    sort_order: int = 0


class PaymentMethodUpdate(Strict):
    kind: AccountKind | None = None
    label: str | None = Field(default=None, min_length=1, max_length=80)
    account_name: str | None = Field(default=None, max_length=120)
    account_number: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    sort_order: int | None = None
