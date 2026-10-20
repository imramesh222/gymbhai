"""Meta's WhatsApp webhook (PLAN.md §19.3).

    GET  /whatsapp/webhook   Meta checks the address: our verify token back,
                             its challenge answered
    POST /whatsapp/webhook   delivery reports (delivered, read, failed) and
                             what members write to our number

No sign-in: Meta signs each POST with our app secret (X-Hub-Signature-256),
and anything unsigned or signed wrongly is refused. A report Meta can't
deliver to us it sends again, and handling one twice changes nothing.
"""

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_db
from app.services.whatsapp import service as whatsapp

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

REFUSED = AppError(403, "forbidden", "Not signed by Meta.")


@router.get("/webhook", response_class=PlainTextResponse)
def verify(
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge", max_length=200)] = "",
) -> str:
    expected = settings.whatsapp_verify_token
    if mode != "subscribe" or not expected or not hmac.compare_digest(token, expected):
        raise REFUSED
    return challenge


async def raw_body(request: Request) -> bytes:
    """The bytes Meta signed, before anything parses them."""
    return await request.body()


@router.post("/webhook")
def webhook(
    request: Request,
    body: bytes = Depends(raw_body),
    db: Session = Depends(get_db),
) -> dict:
    if not whatsapp.signature_ok(body, request.headers.get("X-Hub-Signature-256")):
        raise REFUSED
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise AppError(400, "bad_request", "Not JSON.") from exc
    if isinstance(payload, dict):
        whatsapp.receive(db, payload)
        db.commit()
    return {"ok": True}
