"""The Meta adapter speaks the Cloud API as published (PLAN.md §19.3)."""

import json

import httpx
import pytest

from app.services.whatsapp.providers import (
    MetaProvider,
    NotOnWhatsApp,
    Outgoing,
    WhatsAppError,
    WhatsAppRejected,
)

MESSAGE = Outgoing(
    to="9812345678",
    template="gymbhai_membership_ends",
    language="en",
    values=["Sita", "Fitness Zone", "1 month", "5 Kartik"],
    button="fitness-zone/renew",
)


def provider(handler) -> tuple[MetaProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return MetaProvider("token-123", "1098765", "v21.0", client), seen


def test_a_template_message() -> None:
    meta, seen = provider(
        lambda r: httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "9779812345678", "wa_id": "9779812345678"}],
                "messages": [{"id": "wamid.HBgLOTc3OTgxMjM0NTY3OBUCABIYFjNFQjA"}],
            },
        )
    )
    sent = meta.send_template(MESSAGE)
    assert sent.provider_ref == "wamid.HBgLOTc3OTgxMjM0NTY3OBUCABIYFjNFQjA"
    request = seen[0]
    assert str(request.url) == "https://graph.facebook.com/v21.0/1098765/messages"
    assert request.headers["Authorization"] == "Bearer token-123"
    body = json.loads(request.content)
    assert body["to"] == "9779812345678"
    assert body["type"] == "template"
    assert body["template"]["name"] == "gymbhai_membership_ends"
    assert body["template"]["language"] == {"code": "en"}
    body_part, button = body["template"]["components"]
    assert [p["text"] for p in body_part["parameters"]] == MESSAGE.values
    assert button == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "fitness-zone/renew"}],
    }


def test_a_free_text_reply() -> None:
    meta, seen = provider(
        lambda r: httpx.Response(200, json={"messages": [{"id": "wamid.reply"}]})
    )
    assert meta.send_text("9812345678", "Hello").provider_ref == "wamid.reply"
    body = json.loads(seen[0].content)
    assert body["type"] == "text" and body["text"]["body"] == "Hello"


def error(code: int, status: int = 400):
    return lambda r: httpx.Response(
        status, json={"error": {"code": code, "message": "nope", "type": "OAuth"}}
    )


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        (131026, 400, NotOnWhatsApp),
        (132001, 400, WhatsAppRejected),  # no such template
        (131008, 400, WhatsAppRejected),  # a parameter missing
        (190, 401, WhatsAppRejected),  # our token expired: SMS at once
        (130429, 400, WhatsAppError),  # throughput: retried
        (131056, 400, WhatsAppError),
        (99999, 503, WhatsAppError),
    ],
)
def test_errors(code: int, status: int, expected: type[Exception]) -> None:
    meta, _ = provider(error(code, status))
    with pytest.raises(expected) as raised:
        meta.send_template(MESSAGE)
    if expected is WhatsAppError:
        assert not isinstance(raised.value, WhatsAppRejected)


def test_meta_unreachable_is_retried() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    meta, _ = provider(down)
    with pytest.raises(WhatsAppError) as raised:
        meta.send_template(MESSAGE)
    assert not isinstance(raised.value, WhatsAppRejected)
