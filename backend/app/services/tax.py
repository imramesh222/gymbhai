"""Tax invoices for VAT-registered gyms (PLAN.md §20.4).

Off on a server until GymBhai is IRD-certified billing software
(TAX_INVOICES_CERTIFIED). Once a gym turns VAT on, each payment gets a tax
invoice in the same transaction, numbered in the gym's fiscal year (from
1 Shrawan) with no gaps; a void or a refund gets a credit note against it.
Nothing issued is changed: the seller, the buyer and the lines are copied.

Prices include VAT: what a member pays is the total, of which 13/113 is VAT.
"""

import datetime as dt
import logging
import uuid
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import sealed
from app.core.calendar import to_bs
from app.core.config import settings
from app.core.errors import AppError
from app.core.time import NEPAL, utcnow
from app.models.gym import Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.payment import KIND_PAYMENT, KIND_REFUND, Payment
from app.models.shop import ProductSale, ProductSaleLine
from app.models.tax import (
    CBMS_OFF,
    CBMS_REFUSED,
    CBMS_SENT,
    CBMS_WAITING,
    CREDIT_NOTE,
    INVOICE,
    GymTax,
    TaxInvoice,
)
from app.models.training import PtPackage

if TYPE_CHECKING:
    from app.schemas.tax import TaxInvoiceRead
from app.services import counters

log = logging.getLogger("gymbhai.tax")

VAT_PERCENT = 13
JOB_CBMS = "tax.cbms"
WALK_IN = "Walk-in"


def available() -> bool:
    """Whether gyms can issue tax invoices at all: only once IRD has
    certified GymBhai, or in local development and tests."""
    return settings.tax_invoices_certified or settings.environment in (
        "local",
        "test",
    )


def of_gym(db: Session, gym_id: uuid.UUID) -> GymTax | None:
    return db.scalar(select(GymTax).where(GymTax.gym_id == gym_id))


def active(db: Session, gym_id: uuid.UUID, on: dt.date) -> GymTax | None:
    """The gym's VAT registration, if invoices are issued on that day."""
    if not available():
        return None
    row = of_gym(db, gym_id)
    if (
        row is None
        or not row.vat_registered
        or not row.pan
        or row.starts_on is None
        or row.starts_on > on
    ):
        return None
    return row


def fiscal_year(day: dt.date) -> str:
    """Nepal's fiscal year, from 1 Shrawan (the 4th BS month): "2083/84"."""
    year, month, _ = to_bs(day)
    first = year if month >= 4 else year - 1
    return f"{first}/{(first + 1) % 100:02d}"


def bs_date(day: dt.date) -> str:
    year, month, date = to_bs(day)
    return f"{year}.{month:02d}.{date:02d}"


def split(total: int) -> tuple[int, int]:
    """(before VAT, VAT) of a total that includes VAT, rounded to the paisa."""
    taxable = (total * 100 + 56) // (100 + VAT_PERCENT)
    return taxable, total - taxable


def _before_vat(lines: list[dict[str, Any]], taxable: int) -> list[dict[str, Any]]:
    """Lines with VAT-inclusive amounts, as the invoice lists them: before
    VAT, adding up to `taxable` exactly (the rounding goes on the largest)."""
    out = []
    for line in lines:
        amount = (
            split(line["amount"])[0]
            if line["amount"] > 0
            else -split(-line["amount"])[0]
        )
        out.append(
            {
                "description": line["description"],
                "quantity": line["quantity"],
                "rate": round(amount / line["quantity"])
                if line["quantity"]
                else amount,
                "amount": amount,
            }
        )
    if out:
        largest = max(out, key=lambda line: line["amount"])
        largest["amount"] += taxable - sum(line["amount"] for line in out)
        if largest["quantity"] == 1:
            largest["rate"] = largest["amount"]
    return out


def _what_for(db: Session, payment: Payment) -> list[dict[str, Any]]:
    """What the payment paid for, as invoice lines (VAT included)."""
    if payment.sale_id:
        sale = db.get(ProductSale, payment.sale_id)
        assert sale is not None
        lines = [
            {
                "description": line.name,
                "quantity": line.quantity,
                "amount": line.unit_price * line.quantity,
            }
            for line in db.scalars(
                select(ProductSaleLine)
                .where(ProductSaleLine.sale_id == sale.id)
                .order_by(ProductSaleLine.name, ProductSaleLine.id)
            )
        ]
        if sale.discount:
            lines.append(
                {"description": "Discount", "quantity": 1, "amount": -sale.discount}
            )
        return lines
    if payment.membership_id:
        membership = db.get(Membership, payment.membership_id)
        assert membership is not None
        text = (
            f"{membership.plan_name} membership, "
            f"{membership.start_date:%d %b %Y} to {membership.end_date:%d %b %Y}"
        )
    else:
        package = db.get(PtPackage, payment.pt_package_id)
        assert package is not None
        text = f"{package.plan_name}, personal training"
    return [{"description": text, "quantity": 1, "amount": payment.amount}]


def _buyer(db: Session, payment: Payment) -> tuple[str, str | None]:
    member = db.get(Member, payment.member_id) if payment.member_id else None
    if member is None:
        return WALK_IN, None
    return member.name, member.address


def _issue(
    db: Session,
    tax: GymTax,
    *,
    kind: str,
    payment: Payment,
    lines: list[dict[str, Any]],
    total: int,
    staff_id: uuid.UUID | None,
    ref: TaxInvoice | None = None,
    reason: str | None = None,
) -> TaxInvoice:
    gym = db.get(Gym, tax.gym_id)
    assert gym is not None
    now = utcnow()
    year = fiscal_year(now.astimezone(NEPAL).date())
    sequence = "tax_inv" if kind == INVOICE else "tax_cn"
    taxable, vat = split(total)
    buyer_name, buyer_address = (
        (ref.buyer_name, ref.buyer_address) if ref else _buyer(db, payment)
    )
    row = TaxInvoice(
        id=uuid.uuid4(),
        gym_id=tax.gym_id,
        kind=kind,
        fiscal_year=year,
        number=counters.next_value(db, tax.gym_id, f"{sequence}:{year}"),
        payment_id=payment.id,
        ref_invoice_id=ref.id if ref else None,
        seller={"name": gym.name, "address": gym.address, "pan": tax.pan},
        buyer_name=buyer_name[:120],
        buyer_address=buyer_address,
        buyer_pan=ref.buyer_pan if ref else None,
        lines=_before_vat(lines, taxable),
        taxable=taxable,
        vat=vat,
        total=total,
        issued_at=now,
        issued_by=staff_id,
        reason=reason,
        cbms_status=CBMS_WAITING if tax.cbms_enabled else CBMS_OFF,
    )
    db.add(row)
    db.flush()
    if tax.cbms_enabled:
        from app.worker import enqueue

        enqueue(db, JOB_CBMS, {"id": str(row.id)})
    return row


# --- when money moves ---------------------------------------------------------------


def on_payment(db: Session, payment: Payment, staff_id: uuid.UUID | None) -> None:
    """A payment of a VAT-registered gym: its invoice, now."""
    if payment.kind == KIND_REFUND:
        return _on_refund(db, payment, staff_id)
    tax = active(db, payment.gym_id, payment.paid_at.astimezone(NEPAL).date())
    if tax is None:
        return None
    _issue(
        db,
        tax,
        kind=INVOICE,
        payment=payment,
        lines=_what_for(db, payment),
        total=payment.amount,
        staff_id=staff_id,
    )
    return None


def invoice_of(db: Session, payment_id: uuid.UUID) -> TaxInvoice | None:
    return db.scalar(
        select(TaxInvoice).where(
            TaxInvoice.payment_id == payment_id, TaxInvoice.kind == INVOICE
        )
    )


def credited(db: Session, invoice: TaxInvoice) -> int:
    """How much of an invoice credit notes have taken back."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(TaxInvoice.total), 0)).where(
                TaxInvoice.ref_invoice_id == invoice.id,
                TaxInvoice.kind == CREDIT_NOTE,
            )
        )
        or 0
    )


def _on_refund(db: Session, refund: Payment, staff_id: uuid.UUID | None) -> None:
    """A refund: a credit note against the newest invoice on the same
    membership or training that still has that much left. None if the money
    was paid before VAT invoices began."""
    target = (
        Payment.membership_id == refund.membership_id
        if refund.membership_id
        else Payment.pt_package_id == refund.pt_package_id
    )
    candidates = db.scalars(
        select(TaxInvoice)
        .join(Payment, Payment.id == TaxInvoice.payment_id)
        .where(
            TaxInvoice.gym_id == refund.gym_id,
            TaxInvoice.kind == INVOICE,
            target,
            Payment.kind == KIND_PAYMENT,
        )
        .order_by(TaxInvoice.issued_at.desc())
    )
    for invoice in candidates:
        if invoice.total - credited(db, invoice) >= refund.amount:
            tax = of_gym(db, refund.gym_id)
            assert tax is not None
            _issue(
                db,
                tax,
                kind=CREDIT_NOTE,
                payment=refund,
                lines=[
                    {
                        "description": f"Refund: {invoice.lines[0]['description']}",
                        "quantity": 1,
                        "amount": refund.amount,
                    }
                ],
                total=refund.amount,
                staff_id=staff_id,
                ref=invoice,
                reason=refund.note or "Refund",
            )
            return


def on_void(
    db: Session, payment: Payment, reason: str, staff_id: uuid.UUID | None
) -> None:
    """A voided payment: its invoice taken back in full by a credit note; a
    voided refund, its credit note undone by a new invoice."""
    tax = of_gym(db, payment.gym_id)
    if tax is None:
        return
    invoice = invoice_of(db, payment.id)
    if invoice is not None:
        left = invoice.total - credited(db, invoice)
        if left > 0:
            _issue(
                db,
                tax,
                kind=CREDIT_NOTE,
                payment=payment,
                lines=[
                    {
                        "description": f"Void: {invoice.lines[0]['description']}",
                        "quantity": 1,
                        "amount": left,
                    }
                ],
                total=left,
                staff_id=staff_id,
                ref=invoice,
                reason=reason,
            )
        return
    note = db.scalar(
        select(TaxInvoice).where(
            TaxInvoice.payment_id == payment.id, TaxInvoice.kind == CREDIT_NOTE
        )
    )
    if note is not None:
        _issue(
            db,
            tax,
            kind=INVOICE,
            payment=payment,
            lines=[
                {
                    "description": f"Refund voided: {note.reason or ''}".strip(),
                    "quantity": 1,
                    "amount": note.total,
                }
            ],
            total=note.total,
            staff_id=staff_id,
            ref=note,
            reason=reason,
        )


def refuse_amount_change(db: Session, payment: Payment) -> None:
    """An invoiced payment's amount is never edited: void it and record it
    again, so the books keep both."""
    if invoice_of(db, payment.id) is not None:
        raise AppError(
            409,
            "invoiced",
            "This payment has a tax invoice: void it and record it again.",
        )


def printed(db: Session, invoice: TaxInvoice) -> int:
    """One more print or download. 1 is the original; later ones, copies."""
    db.refresh(invoice, with_for_update=True)
    invoice.prints += 1
    invoice.last_printed_at = utcnow()
    return invoice.prints


# --- CBMS ---------------------------------------------------------------------------


def cbms_payload(invoice: TaxInvoice, tax: GymTax, password: str) -> dict[str, Any]:
    """A bill or a credit note as IRD's CBMS takes it: rupees, BS dates,
    the fiscal year as "2083.084" (community clients of the API; IRD
    publishes no documents)."""
    first, second = invoice.fiscal_year.split("/")
    day = invoice.issued_at.astimezone(NEPAL)
    body: dict[str, Any] = {
        "username": tax.cbms_username,
        "password": password,
        "seller_pan": tax.pan,
        "buyer_pan": invoice.buyer_pan or "",
        "buyer_name": invoice.buyer_name,
        "fiscal_year": f"{first}.0{second}",
        "total_sales": invoice.total / 100,
        "taxable_sales_vat": invoice.taxable / 100,
        "vat": invoice.vat / 100,
        "excisable_amount": 0,
        "excise": 0,
        "taxable_sales_hst": 0,
        "hst": 0,
        "amount_for_esf": 0,
        "esf": 0,
        "export_sales": 0,
        "tax_exempted_sales": 0,
        "isrealtime": True,
        "datetimeClient": day.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if invoice.kind == INVOICE:
        body["invoice_number"] = str(invoice.number)
        body["invoice_date"] = bs_date(day.date())
    else:
        body["credit_note_number"] = str(invoice.number)
        body["credit_note_date"] = bs_date(day.date())
        body["reason_for_return"] = invoice.reason or "Return"
    return body


class CbmsRefused(Exception):
    """CBMS refused the bill for good (credentials, a bad field)."""


def _post(path: str, body: dict[str, Any]) -> int:
    if settings.cbms_provider == "console":
        log.info(
            "CBMS %s: %s", path, {k: v for k, v in body.items() if k != "password"}
        )
        return 200
    response = httpx.post(
        f"{settings.cbms_url.rstrip('/')}{path}", json=body, timeout=20
    )
    response.raise_for_status()
    answer = response.json()
    if isinstance(answer, dict):
        answer = answer.get("code", answer.get("status"))
    return int(answer)


def handle_cbms(db: Session, payload: dict[str, Any]) -> None:
    """The worker sends one bill; CBMS down is retried by the worker."""
    invoice = db.get(TaxInvoice, uuid.UUID(payload["id"]))
    if invoice is None or invoice.cbms_status == CBMS_SENT:
        return
    tax = of_gym(db, invoice.gym_id)
    if tax is None or not tax.cbms_enabled or not tax.cbms_secret:
        invoice.cbms_status = CBMS_OFF
        return
    password = sealed.open_sealed(tax.cbms_secret, tax.id)["password"]
    path = "/api/bill" if invoice.kind == INVOICE else "/api/billreturn"
    code = _post(path, cbms_payload(invoice, tax, password))
    # 101 for a bill: CBMS has it already (an earlier try got through).
    if code == 200 or (code == 101 and invoice.kind == INVOICE):
        invoice.cbms_status = CBMS_SENT
        invoice.cbms_sent_at = utcnow()
        invoice.cbms_error = None
        return
    if code in (100, 104, 105) or (code == 101 and invoice.kind == CREDIT_NOTE):
        invoice.cbms_status = CBMS_REFUSED
        invoice.cbms_error = CBMS_CODES.get(code, str(code))
        if code == 100:
            tax.cbms_error = invoice.cbms_error
        return
    raise RuntimeError(f"CBMS answered {code}")  # 102, 103: tried again


def give_up_cbms(db: Session, payload: dict[str, Any], error: str) -> None:
    invoice = db.get(TaxInvoice, uuid.UUID(payload["id"]))
    if invoice is not None and invoice.cbms_status == CBMS_WAITING:
        invoice.cbms_status = CBMS_REFUSED
        invoice.cbms_error = error.strip().splitlines()[-1][:500]


CBMS_CODES = {
    100: "CBMS refused the username and password.",
    101: "CBMS has no bill with that number to return.",
    104: "CBMS found a field it couldn't read.",
    105: "CBMS has no bill with that number to return.",
}


# --- in words -----------------------------------------------------------------------

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    words = []
    if hundreds:
        words.append(f"{_ONES[hundreds]} hundred")
    if rest:
        words.append(_below_hundred(rest))
    return " ".join(words)


def _words(n: int) -> str:
    """A whole number of crore (or anything), in lakh and thousand."""
    lakh, rest = divmod(n, 1_00_000)
    thousand, rest = divmod(rest, 1000)
    parts = []
    if lakh:
        parts.append(
            f"{_words(lakh)} lakh" if lakh >= 100 else f"{_below_hundred(lakh)} lakh"
        )
    if thousand:
        parts.append(f"{_below_hundred(thousand)} thousand")
    if rest:
        parts.append(_below_thousand(rest))
    return " ".join(parts) or "zero"


def in_words(paisa: int) -> str:
    """As Nepali invoices write totals, in lakh and crore:
    "One lakh thirteen thousand rupees and fifty paisa only"."""
    rupees, cents = divmod(paisa, 100)
    parts = []
    crore, rest = divmod(rupees, 1_00_00_000)
    lakh, rest = divmod(rest, 1_00_000)
    thousand, rest = divmod(rest, 1000)
    if crore:
        parts.append(f"{_words(crore)} crore")
    if lakh:
        parts.append(f"{_below_hundred(lakh)} lakh")
    if thousand:
        parts.append(f"{_below_hundred(thousand)} thousand")
    if rest:
        parts.append(_below_thousand(rest))
    text = " ".join(parts) or "zero"
    text = f"{text} {'rupee' if rupees == 1 else 'rupees'}"
    if cents:
        text += f" and {_below_hundred(cents)} paisa"
    return (text + " only").capitalize()


# --- reading ------------------------------------------------------------------------


def reads(db: Session, rows: list[TaxInvoice]) -> list["TaxInvoiceRead"]:
    from app.schemas.tax import TaxInvoiceRead, TaxLine

    refs = {
        r.id: r
        for r in (
            db.scalars(
                select(TaxInvoice).where(
                    TaxInvoice.id.in_(
                        {r.ref_invoice_id for r in rows if r.ref_invoice_id}
                    )
                )
            )
            if any(r.ref_invoice_id for r in rows)
            else []
        )
    }
    out = []
    for row in rows:
        ref = refs.get(row.ref_invoice_id) if row.ref_invoice_id else None
        out.append(
            TaxInvoiceRead(
                id=row.id,
                kind=row.kind,  # type: ignore[arg-type]
                fiscal_year=row.fiscal_year,
                number=row.number,
                payment_id=row.payment_id,
                ref_number=ref.number if ref else None,
                ref_fiscal_year=ref.fiscal_year if ref else None,
                seller=row.seller,
                buyer_name=row.buyer_name,
                buyer_address=row.buyer_address,
                buyer_pan=row.buyer_pan,
                lines=[TaxLine(**line) for line in row.lines],
                taxable=row.taxable,
                vat=row.vat,
                total=row.total,
                total_in_words=in_words(row.total),
                issued_at=row.issued_at,
                issued_on_bs=bs_date(row.issued_at.astimezone(NEPAL).date()),
                reason=row.reason,
                prints=row.prints,
                cbms_status=row.cbms_status,
            )
        )
    return out


def of_payment(db: Session, payment_id: uuid.UUID) -> list[TaxInvoice]:
    """Every tax document made with this payment: its invoice, the credit
    note of its void or of its refund, a refund's void's new invoice."""
    return list(
        db.scalars(
            select(TaxInvoice)
            .where(TaxInvoice.payment_id == payment_id)
            .order_by(TaxInvoice.issued_at, TaxInvoice.number)
        )
    )
