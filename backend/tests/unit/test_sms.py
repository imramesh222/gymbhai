import httpx
import pytest

from app.core.sms_text import is_gsm, render, segments
from app.services.sms.providers import (
    AakashProvider,
    SmsError,
    SmsRejected,
    SparrowProvider,
)


def test_gsm_messages_hold_160_characters() -> None:
    assert segments("a" * 160) == 1
    assert segments("a" * 161) == 2
    assert segments("a" * 306) == 2
    assert segments("a" * 307) == 3


def test_nepali_is_unicode_and_holds_70() -> None:
    namaste = "नमस्ते"  # 6 UTF-16 units
    assert not is_gsm(namaste)
    assert segments(namaste * 11 + "न") == 1  # 67 units
    assert segments(namaste * 12) == 2  # 72 units


def test_one_nepali_letter_makes_the_whole_message_unicode() -> None:
    assert segments("a" * 100) == 1
    assert segments("a" * 100 + "न") == 2


def test_extended_characters_cost_two() -> None:
    assert segments("€" * 80) == 1
    assert segments("€" * 81) == 2


def test_render_fills_known_placeholders_only() -> None:
    assert render("Hi {name}, see {link} {oops}", {"name": "Sita", "link": "x"}) == (
        "Hi Sita, see x {oops}"
    )


def transport(status: int, body: dict) -> httpx.Client:
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(status, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    client.seen = seen  # type: ignore[attr-defined]
    return client


def test_sparrow_sends_the_documented_fields() -> None:
    # The documented answer: queued, with nothing identifying the message.
    client = transport(
        200, {"count": 1, "response_code": 200, "response": "1 messages queued"}
    )
    sent = SparrowProvider("tok", "InfoSMS", client).send("9841000001", "Hi")
    assert sent.provider_ref is None
    assert client.seen["url"] == "https://api.sparrowsms.com/v2/sms/"  # type: ignore[attr-defined]
    assert client.seen["form"] == {  # type: ignore[attr-defined]
        "token": "tok",
        "from": "InfoSMS",
        "to": "9841000001",
        "text": "Hi",
    }


def test_sparrow_refusal_is_an_error() -> None:
    client = transport(403, {"response_code": 1002, "response": "Invalid token"})
    with pytest.raises(SmsError, match="Invalid token"):
        SparrowProvider("bad", "InfoSMS", client).send("9841000001", "Hi")


def test_sparrow_rejects_this_message_for_good() -> None:
    """A bad number is refused the same way every time: no retries."""
    client = transport(200, {"response_code": 1007, "response": "Invalid Receiver"})
    with pytest.raises(SmsRejected):
        SparrowProvider("tok", "InfoSMS", client).send("9800000000", "Hi")


def test_sparrow_out_of_credit_is_worth_retrying() -> None:
    client = transport(200, {"response_code": 1013, "response": "Insufficient Credits"})
    with pytest.raises(SmsError) as refused:
        SparrowProvider("tok", "InfoSMS", client).send("9841000001", "Hi")
    assert not isinstance(refused.value, SmsRejected)


def test_sparrow_reads_the_credit_balance() -> None:
    client = transport(
        200, {"credits_available": 250, "credits_consumed": 12, "response_code": 200}
    )
    assert SparrowProvider("tok", "InfoSMS", client).credits() == 250
    assert client.seen["url"] == (  # type: ignore[attr-defined]
        "https://api.sparrowsms.com/v2/credit/?token=tok"
    )


def test_aakash_sends_and_reads_the_reference() -> None:
    client = transport(
        200,
        {
            "error": False,
            "message": "ok",
            "data": {"valid": [{"id": 7}], "invalid": []},
        },
    )
    assert AakashProvider("tok", client).send("9841000001", "Hi").provider_ref == "7"


def test_aakash_invalid_number_is_an_error() -> None:
    client = transport(
        200,
        {
            "error": False,
            "message": "none valid",
            "data": {"valid": [], "invalid": [1]},
        },
    )
    with pytest.raises(SmsError):
        AakashProvider("tok", client).send("9841000001", "Hi")
