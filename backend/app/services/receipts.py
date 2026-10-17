"""Payment receipts: what they say, and the PDF to share (PLAN.md §10, §16.3 8.4).

A receipt, not a VAT invoice, and it says so. The PDF is A5 and carries the
gym's details, so a member can forward it anywhere.
"""

import datetime as dt
from functools import cache
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
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
from app.schemas.money import Receipt, ReceiptLink
from app.services import memberships as ms

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
    "period": "Membership",
    "method": "Paid by",
    "refund_method": "Refunded by",
    "reference": "Transaction ID",
    "amount": "Amount received",
    "refund_amount": "Amount refunded",
    "owed": "Still owed",
    "received_by": "Received by",
    "void": "VOID",
    "not_invoice": "This is a payment receipt, not a VAT invoice.",
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
    member = db.get(Member, payment.member_id)
    assert gym is not None and member is not None
    membership = (
        db.get(Membership, payment.membership_id) if payment.membership_id else None
    )
    branch = db.get(Branch, membership.branch_id) if membership else None
    dues_after = None
    if membership is not None:
        dues_after = ms.dues_of(membership, ms.payments_for(db, [membership.id]))
    return Receipt(
        payment=payments_read(db, [payment])[0],
        gym_name=gym.name,
        gym_phone=gym.phone,
        gym_address=gym.address,
        branch_name=branch.name if branch else None,
        member_name=member.name,
        member_code=member.member_code,
        member_phone=member.phone,
        plan_name=membership.plan_name if membership else None,
        start_date=membership.start_date if membership else None,
        end_date=membership.end_date if membership else None,
        membership_total=ms.amount_due(membership) if membership else None,
        dues_after=dues_after,
        date_display=gym.config.date_display,
    )


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
        (TEXT["member"], f"{receipt.member_name} ({receipt.member_code})"),
    ]
    if receipt.plan_name:
        rows.append((TEXT["plan"], receipt.plan_name))
    if receipt.start_date and receipt.end_date:
        rows.append(
            (
                TEXT["period"],
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
