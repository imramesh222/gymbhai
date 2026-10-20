"""Payment receipts: what they say, and the PDF to share (PLAN.md §10, §16.3 8.4).

A receipt, not a VAT invoice, and it says so; but for a VAT-registered gym
(§20.4) the PDF is the payment's tax invoice, and any credit note, instead.
The PDF is A5 and carries the gym's details, so a member can forward it
anywhere.
"""

import datetime as dt
from functools import cache
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.presenters import payments_read
from app.core import signed_links
from app.core.calendar import format_date
from app.core.config import settings
from app.core.time import NEPAL
from app.models.gym import Branch, Gym
from app.models.member import Member
from app.models.membership import Membership
from app.models.payment import KIND_REFUND, Payment
from app.models.shop import ProductSale
from app.models.training import PtPackage
from app.schemas.money import Receipt, ReceiptItem, ReceiptLink
from app.schemas.tax import TaxInvoiceRead
from app.services import memberships as ms
from app.services import shop, tax
from app.services.whatsapp import service as whatsapp

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
LINK_DAYS = 30

# The receipt's words: English at launch, in one place for Nepali later.
TEXT = {
    "title": "Payment receipt",
    "refund_title": "Refund receipt",
    "number": "Receipt no.",
    "date": "Date",
    "member": "Member",
    "plan": "Plan",
    "covers": "Also covers",
    "period": "Membership",
    "training": "Personal training",
    "method": "Paid by",
    "refund_method": "Refunded by",
    "reference": "Transaction ID",
    "amount": "Amount received",
    "refund_amount": "Amount refunded",
    "owed": "Still owed",
    "received_by": "Received by",
    "void": "VOID",
    "walk_in": "Walk-in",
    "bought": "Bought",
    "discount": "Discount",
    "not_invoice": "This is a payment receipt, not a VAT invoice.",
    # A VAT-registered gym's (§20.4).
    "tax_invoice": "Tax invoice",
    "credit_note": "Credit note (sales return)",
    "copy": "Copy of original ({n})",
    "pan": "PAN",
    "invoice_no": "Invoice no.",
    "credit_no": "Credit note no.",
    "against": "Against invoice no.",
    "fiscal_year": "Fiscal year",
    "buyer": "Buyer",
    "buyer_pan": "Buyer's PAN",
    "reason": "Reason",
    "description": "Description",
    "qty": "Qty",
    "rate": "Rate",
    "line_amount": "Amount",
    "taxable": "Taxable amount",
    "vat": "VAT 13%",
    "total": "Total",
    "in_words": "In words",
}
METHODS = {
    "cash": "Cash",
    "esewa": "eSewa",
    "khalti": "Khalti",
    "fonepay": "Fonepay",
    "bank": "Bank transfer",
}


def build(db: Session, payment: Payment) -> Receipt:
    gym = db.get(Gym, payment.gym_id)
    # Nobody, for a walk-in's purchase at the desk (§20.1).
    member = db.get(Member, payment.member_id) if payment.member_id else None
    assert gym is not None
    # What it paid for: a membership, or personal training (§18.3).
    bought: Membership | PtPackage | None = None
    if payment.membership_id:
        bought = db.get(Membership, payment.membership_id)
    elif payment.pt_package_id:
        bought = db.get(PtPackage, payment.pt_package_id)
    sale = db.get(ProductSale, payment.sale_id) if payment.sale_id else None
    branch_id = bought.branch_id if bought else (sale.branch_id if sale else None)
    branch = db.get(Branch, branch_id) if branch_id else None
    items = (
        [
            ReceiptItem(
                name=line.name, quantity=line.quantity, unit_price=line.unit_price
            )
            for line in shop.lines_for(db, [sale.id])[sale.id]
        ]
        if sale
        else []
    )
    dues_after = None
    total = None
    if bought is not None:
        dues_after = ms.owed(bought, ms.payments_on(db, bought))
        total = (
            ms.amount_due(bought)
            if isinstance(bought, Membership)
            else bought.price - bought.discount
        )
    return Receipt(
        payment=payments_read(db, [payment])[0],
        gym_name=gym.name,
        gym_phone=gym.phone,
        gym_address=gym.address,
        branch_name=branch.name if branch else None,
        member_name=member.name if member else None,
        member_code=member.member_code if member else None,
        member_phone=member.phone if member else None,
        plan_name=bought.plan_name if bought else None,
        start_date=bought.start_date if bought else None,
        end_date=bought.end_date if bought else None,
        membership_total=total,
        dues_after=dues_after,
        date_display=gym.config.date_display,
        training=isinstance(bought, PtPackage),
        covers=_covers(db, bought),
        whatsapp=member is not None
        and whatsapp.reachable(gym, member)
        and payment.voided_at is None,
        items=items,
        discount=sale.discount if sale else 0,
        tax_documents=tax.reads(db, tax.of_payment(db, payment.id)),
    )


def _covers(db: Session, bought: Membership | PtPackage | None) -> list[str]:
    """Everyone else a family or couple plan's payment covers (§19.1)."""
    if not isinstance(bought, Membership) or bought.group_id is None:
        return []
    ids = [
        m.member_id
        for m in ms.group_memberships(db, bought.group_id)
        if m.member_id != bought.member_id and m.cancelled_at is None
    ]
    if not ids:
        return []
    names = dict(
        db.execute(select(Member.id, Member.name).where(Member.id.in_(ids))).all()
    )
    return [names[i] for i in ids if i in names]


def rupees(paisa: int) -> str:
    """Nepali grouping, as on screen: Rs 1,00,000.50 (PLAN.md §10)."""
    sign = "−" if paisa < 0 else ""
    whole, part = divmod(abs(paisa), 100)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join([*groups, tail]) if groups else tail
    return f"{sign}Rs {text}" + (f".{part:02d}" if part else "")


def filename(receipt: Receipt) -> str:
    return f"receipt-{receipt.payment.receipt_no}.pdf"


@cache
def _font_paths() -> dict[str, Path]:
    return {
        "": FONTS / "NotoSans-Regular.ttf",
        "B": FONTS / "NotoSans-Bold.ttf",
        "dev": FONTS / "NotoSansDevanagari-Regular.ttf",
        "devB": FONTS / "NotoSansDevanagari-Bold.ttf",
    }


def pdf(receipt: Receipt) -> bytes:
    """The receipt; for a VAT-registered gym's payment, its tax invoice and
    any credit note instead, a page each (§20.4)."""
    if receipt.tax_documents:
        doc = _document(receipt)
        for document in receipt.tax_documents:
            _tax_page(doc, receipt, document)
        return bytes(doc.output())
    return _receipt_pdf(receipt)


def _document(receipt: Receipt) -> FPDF:
    doc = FPDF(format=(148, 210))  # A5, in mm
    doc.set_title(f"{receipt.gym_name} — {filename(receipt)}")
    doc.set_author(receipt.gym_name)
    fonts = _font_paths()
    doc.add_font("Noto", "", fonts[""])
    doc.add_font("Noto", "B", fonts["B"])
    doc.add_font("NotoDev", "", fonts["dev"])
    doc.add_font("NotoDev", "B", fonts["devB"])
    doc.set_fallback_fonts(["NotoDev"], exact_match=False)
    doc.set_text_shaping(True)
    doc.set_margins(12, 12, 12)
    doc.set_auto_page_break(True, 12)
    return doc


def _tax_page(doc: FPDF, receipt: Receipt, document: TaxInvoiceRead) -> None:
    """One tax invoice or credit note, laid out as the VAT Rules ask: the
    seller and their PAN, the number in its fiscal year, the dates in BS and
    AD, the buyer, the lines before VAT, the taxable amount, VAT and total."""
    doc.add_page()
    width = doc.epw
    credit = document.kind == "credit_note"
    seller = document.seller

    def centred(text: str, size: float, style: str = "") -> None:
        doc.set_font("Noto", style, size)
        doc.multi_cell(
            width, size * 0.5, text, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )

    centred(seller.get("name") or receipt.gym_name, 15, "B")
    if seller.get("address"):
        centred(seller["address"], 9)
    centred(f"{TEXT['pan']}: {seller.get('pan') or ''}", 9)
    doc.ln(2)
    centred(TEXT["credit_note" if credit else "tax_invoice"].upper(), 11, "B")
    if document.prints > 1:
        centred(TEXT["copy"].format(n=document.prints), 9)
    doc.ln(2)

    issued = document.issued_at.astimezone(NEPAL)
    rows = [
        (TEXT["credit_no" if credit else "invoice_no"], str(document.number)),
        (TEXT["fiscal_year"], document.fiscal_year),
        (
            TEXT["date"],
            f"{document.issued_on_bs} BS ({issued:%d %b %Y}), {issued:%H:%M}",
        ),
        (TEXT["number"], f"#{receipt.payment.receipt_no}"),
    ]
    if credit and document.ref_number is not None:
        rows.append(
            (TEXT["against"], f"{document.ref_number} ({document.ref_fiscal_year})")
        )
    rows.append((TEXT["buyer"], document.buyer_name))
    if document.buyer_address:
        rows.append(("", document.buyer_address))
    if document.buyer_pan:
        rows.append((TEXT["buyer_pan"], document.buyer_pan))
    if credit and document.reason:
        rows.append((TEXT["reason"], document.reason))
    rows.append(
        (TEXT["method"], METHODS.get(receipt.payment.method, receipt.payment.method))
    )
    label_width = width * 0.34
    for label, value in rows:
        doc.set_font("Noto", "", 9)
        doc.set_text_color(100, 116, 139)
        y = doc.get_y()
        doc.cell(label_width, 5.5, label)
        doc.set_xy(doc.l_margin + label_width, y)
        doc.set_text_color(15, 23, 42)
        doc.multi_cell(
            width - label_width, 5.5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
    doc.ln(2)

    columns = (width * 0.52, width * 0.1, width * 0.19, width * 0.19)
    doc.set_font("Noto", "B", 8.5)
    doc.set_fill_color(241, 245, 249)
    for text, w, align in zip(
        (TEXT["description"], TEXT["qty"], TEXT["rate"], TEXT["line_amount"]),
        columns,
        ("L", "R", "R", "R"),
        strict=True,
    ):
        doc.cell(w, 6, text, align=align, fill=True)
    doc.ln(6)
    doc.set_font("Noto", "", 8.5)
    for line in document.lines:
        y = doc.get_y()
        doc.multi_cell(
            columns[0], 5, line.description, new_x=XPos.RIGHT, new_y=YPos.TOP
        )
        height = max(doc.get_y() - y, 5)
        doc.set_xy(doc.l_margin + columns[0], y)
        doc.cell(columns[1], 5, str(line.quantity), align="R")
        doc.cell(columns[2], 5, rupees(line.rate), align="R")
        doc.cell(columns[3], 5, rupees(line.amount), align="R")
        doc.set_xy(doc.l_margin, y + max(height, 5))
    doc.ln(2)

    for label, amount, style in (
        (TEXT["taxable"], document.taxable, ""),
        (TEXT["vat"], document.vat, ""),
        (TEXT["total"], document.total, "B"),
    ):
        doc.set_font("Noto", style, 10 if style else 9)
        doc.cell(width * 0.62, 6, label, align="R")
        doc.cell(
            width * 0.38,
            6,
            rupees(amount),
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    doc.ln(1)
    doc.set_font("Noto", "", 8.5)
    doc.multi_cell(
        width,
        4.5,
        f"{TEXT['in_words']}: {document.total_in_words}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    if receipt.payment.received_by_name:
        doc.ln(2)
        doc.cell(width, 5, f"{TEXT['received_by']} {receipt.payment.received_by_name}")


def _receipt_pdf(receipt: Receipt) -> bytes:
    p = receipt.payment
    display = receipt.date_display  # type: ignore[arg-type]
    refund = p.kind == KIND_REFUND
    doc = FPDF(format=(148, 210))  # A5, in mm
    doc.set_title(f"{receipt.gym_name} — {filename(receipt)}")
    doc.set_author(receipt.gym_name)
    fonts = _font_paths()
    doc.add_font("Noto", "", fonts[""])
    doc.add_font("Noto", "B", fonts["B"])
    doc.add_font("NotoDev", "", fonts["dev"])
    doc.add_font("NotoDev", "B", fonts["devB"])
    # Names typed in Nepali: Devanagari from its own font, shaped properly.
    doc.set_fallback_fonts(["NotoDev"], exact_match=False)
    doc.set_text_shaping(True)
    doc.set_margins(14, 14, 14)
    doc.set_auto_page_break(True, 14)
    doc.add_page()
    width = doc.epw

    def line(text: str, size: float, style: str = "", gap: float = 0) -> None:
        doc.set_font("Noto", style, size)
        doc.multi_cell(
            width, size * 0.5, text, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        if gap:
            doc.ln(gap)

    line(receipt.gym_name, 16, "B", 1)
    for extra in (receipt.branch_name, receipt.gym_address, receipt.gym_phone):
        if extra:
            line(extra, 9.5)
    doc.ln(3)
    line(TEXT["refund_title" if refund else "title"].upper(), 10, "B", 2)
    doc.set_draw_color(203, 213, 225)

    def rule() -> None:
        doc.set_dash_pattern(dash=1, gap=1)
        doc.line(doc.l_margin, doc.get_y(), doc.l_margin + width, doc.get_y())
        doc.set_dash_pattern()

    rule()
    doc.ln(3)

    if p.voided_at:
        doc.set_fill_color(254, 226, 226)
        doc.set_text_color(153, 27, 27)
        doc.set_font("Noto", "B", 10)
        reason = f"{TEXT['void']} — {p.void_reason}" if p.void_reason else TEXT["void"]
        doc.multi_cell(
            width, 7, reason, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        doc.set_text_color(15, 23, 42)
        doc.ln(2)

    paid_at = p.paid_at.astimezone(NEPAL)
    rows = [
        (TEXT["number"], f"#{p.receipt_no}"),
        (TEXT["date"], f"{format_date(paid_at.date(), display)}, {paid_at:%H:%M}"),
        (
            TEXT["member"],
            f"{receipt.member_name} ({receipt.member_code})"
            if receipt.member_name
            else TEXT["walk_in"],
        ),
    ]
    if receipt.items:
        rows.append(
            (
                TEXT["bought"],
                "\n".join(
                    f"{item.quantity} × {item.name} @ {rupees(item.unit_price)}"
                    for item in receipt.items
                ),
            )
        )
    if receipt.discount:
        rows.append((TEXT["discount"], rupees(receipt.discount)))
    if receipt.plan_name:
        rows.append((TEXT["plan"], receipt.plan_name))
    if receipt.covers:
        rows.append((TEXT["covers"], ", ".join(receipt.covers)))
    if receipt.start_date and receipt.end_date:
        rows.append(
            (
                TEXT["training" if receipt.training else "period"],
                f"{format_date(receipt.start_date, display)} –\n"
                f"{format_date(receipt.end_date, display)}",
            )
        )
    rows.append(
        (TEXT["refund_method" if refund else "method"], METHODS.get(p.method, p.method))
    )
    if p.transaction_ref:
        rows.append((TEXT["reference"], p.transaction_ref))

    label_width = width * 0.36
    for label, value in rows:
        doc.set_font("Noto", "", 9.5)
        doc.set_text_color(100, 116, 139)
        y = doc.get_y()
        doc.cell(label_width, 6, label)
        doc.set_xy(doc.l_margin + label_width, y)
        doc.set_text_color(15, 23, 42)
        doc.multi_cell(
            width - label_width,
            6,
            value,
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        doc.ln(0.5)

    doc.ln(2)
    rule()
    doc.ln(3)
    y = doc.get_y()
    doc.set_font("Noto", "B", 11)
    doc.cell(width / 2, 10, TEXT["refund_amount" if refund else "amount"])
    doc.set_xy(doc.l_margin + width / 2, y)
    doc.set_font("Noto", "B", 18)
    doc.cell(
        width / 2, 10, rupees(p.amount), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    if receipt.dues_after:
        doc.set_font("Noto", "", 9.5)
        doc.set_text_color(146, 64, 14)
        doc.cell(
            width,
            6,
            f"{TEXT['owed']}: {rupees(receipt.dues_after)}",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        doc.set_text_color(15, 23, 42)
    if p.received_by_name:
        doc.ln(3)
        doc.set_font("Noto", "", 9.5)
        doc.cell(
            width,
            6,
            f"{TEXT['received_by']} {p.received_by_name}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    doc.ln(8)
    doc.set_font("Noto", "", 8)
    doc.set_text_color(100, 116, 139)
    doc.multi_cell(
        width, 4.5, TEXT["not_invoice"], align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    return bytes(doc.output())


LINK_KIND = "receipt"


def share(receipt: Receipt) -> ReceiptLink:
    """A link anyone can open for LINK_DAYS: what Share sends (§16.3, 8.4)."""
    payment_id = receipt.payment.id
    expires, signature = signed_links.sign(LINK_KIND, payment_id, LINK_DAYS)
    url = (
        f"{settings.public_app_url.rstrip('/')}{settings.api_v1_prefix}"
        f"/receipts/{payment_id}.pdf?exp={expires}&sig={signature}"
    )
    title = TEXT["refund_title" if receipt.payment.kind == KIND_REFUND else "title"]
    return ReceiptLink(
        url=url,
        filename=filename(receipt),
        text=f"{receipt.gym_name}: {title} #{receipt.payment.receipt_no}, "
        f"{rupees(receipt.payment.amount)}",
        expires_at=dt.datetime.fromtimestamp(expires, dt.UTC),
    )


def count_prints(db: Session, payment: Payment) -> None:
    """Each print or download of a tax invoice is counted: the first is the
    original, the rest say "Copy of original" (§20.4)."""
    for document in tax.of_payment(db, payment.id):
        tax.printed(db, document)
