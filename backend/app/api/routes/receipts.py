"""Receipts as PDF, opened from a shared link (PLAN.md §16.3, 8.4)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import signed_links
from app.core.errors import not_found
from app.db.session import get_db
from app.models.payment import Payment
from app.services import receipts

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.get("/{payment_id}.pdf")
def receipt_pdf(
    payment_id: uuid.UUID,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query(max_length=64)],
    db: Session = Depends(get_db),
) -> Response:
    """No sign-in: the signature is the permission, issued to staff of the gym
    or to the member the payment is theirs (receipts.share)."""
    if not signed_links.valid(receipts.LINK_KIND, payment_id, exp, sig):
        raise not_found("This receipt link has expired. Ask for a new one.")
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise not_found("Receipt not found.")
    receipt = receipts.build(db, payment)
    return Response(
        content=receipts.pdf(receipt),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{receipts.filename(receipt)}"',
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
