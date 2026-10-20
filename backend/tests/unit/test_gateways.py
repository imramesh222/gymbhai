"""The wallet adapters (PLAN.md §20.2): what each sends, and how it reads the
answers, as their developer documents describe them. No wallet is called."""

import base64
import hashlib
import hmac
import json
import uuid

import httpx
import pytest

from app.core import sealed
from app.services.gateways.providers import (
    FAILED,
    PAID,
    PENDING,
    Esewa,
    Fonepay,
    GatewayError,
    Keys,
    KeysRefused,
    Khalti,
    Order,
    paisa_of,
    rupees,
)

ORDER = Order(
    id="A1B2C3D4E5F6A7B8C9D0",
    amount=1500_00,
    name="1 month, Fitness Zone",
    return_url="https://gymbhai.com/pay/t/back",
    failure_url="https://gymbhai.com/pay/t/cancelled",
    website_url="https://gymbhai.com",
    customer_name="Sita Rai",
    customer_phone="9812345678",
)


def client(answer):
    """An httpx client whose every request gets `answer(request)`."""
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def test_rupees_as_the_wallets_take_them() -> None:
    assert rupees(1500_00) == "1500"
    assert rupees(1500_50) == "1500.50"
    assert rupees(5) == "0.05"
    assert paisa_of("1500.0") == 1500_00
    assert paisa_of(1500.5) == 1500_50
    assert paisa_of("1,500.00") == 1500_00
    assert paisa_of(None) is None


# --- eSewa -----------------------------------------------------------------------

ESEWA = Keys(merchant="EPAYTEST", secret={"secret_key": "8gBm/:&EnhH.1/q"}, test=True)


def test_esewa_signs_the_three_fields_in_their_order() -> None:
    checkout = Esewa(httpx.Client()).start(ESEWA, ORDER)
    fields = checkout.fields
    assert checkout.kind == "form"
    assert checkout.url == "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
    assert fields["signed_field_names"] == "total_amount,transaction_uuid,product_code"
    message = (
        "total_amount=1500,transaction_uuid=A1B2C3D4E5F6A7B8C9D0,product_code=EPAYTEST"
    )
    expected = base64.b64encode(
        hmac.new(b"8gBm/:&EnhH.1/q", message.encode(), hashlib.sha256).digest()
    ).decode()
    assert fields["signature"] == expected
    assert (fields["amount"], fields["total_amount"], fields["tax_amount"]) == (
        "1500",
        "1500",
        "0",
    )
    assert fields["success_url"] == ORDER.return_url
    assert fields["failure_url"] == ORDER.failure_url
    live = Esewa(httpx.Client()).start(
        Keys(merchant="NP-ES-GYM", secret={"secret_key": "x"}, test=False), ORDER
    )
    assert live.url == "https://epay.esewa.com.np/api/epay/main/v2/form"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("COMPLETE", PAID),
        ("PENDING", PENDING),
        ("AMBIGUOUS", PENDING),
        ("NOT_FOUND", PENDING),
        ("CANCELED", FAILED),
        ("FULL_REFUND", FAILED),
    ],
)
def test_esewa_status(status: str, expected: str) -> None:
    http, seen = client(
        lambda r: httpx.Response(
            200,
            json={
                "product_code": "EPAYTEST",
                "transaction_uuid": ORDER.id,
                "total_amount": 1500.0,
                "status": status,
                "ref_id": "0001TS9" if status == "COMPLETE" else None,
            },
        )
    )
    answer = Esewa(http).check(ESEWA, ORDER, {})
    assert answer.status == expected
    if expected == PAID:
        assert (answer.transaction_ref, answer.amount) == ("0001TS9", 1500_00)
    [request] = seen
    assert request.url.host == "rc.esewa.com.np"
    assert request.url.path == "/api/epay/transaction/status/"
    assert dict(request.url.params) == {
        "product_code": "EPAYTEST",
        "total_amount": "1500",
        "transaction_uuid": ORDER.id,
    }


def test_esewa_down_or_refusing() -> None:
    http, _ = client(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(GatewayError):
        Esewa(http).check(ESEWA, ORDER, {})
    http, _ = client(
        lambda r: httpx.Response(400, json={"code": 0, "error_message": "Invalid"})
    )
    with pytest.raises(KeysRefused):
        Esewa(http).check(ESEWA, ORDER, {})


# --- Khalti ----------------------------------------------------------------------

KHALTI = Keys(merchant=None, secret={"secret_key": "live_secret_key_abc"}, test=True)


def test_khalti_starts_with_paisa_and_the_key() -> None:
    http, seen = client(
        lambda r: httpx.Response(
            200,
            json={
                "pidx": "bZQLD9wRVWo4CdESSfuSsB",
                "payment_url": "https://test-pay.khalti.com/?pidx=bZQLD9wRVWo4CdESSfuSsB",
                "expires_at": "2026-10-20T18:00:00+05:45",
                "expires_in": 1800,
            },
        )
    )
    checkout = Khalti(http).start(KHALTI, ORDER)
    assert checkout.kind == "redirect"
    assert checkout.reference == "bZQLD9wRVWo4CdESSfuSsB"
    assert checkout.url and "pidx=" in checkout.url
    [request] = seen
    assert str(request.url) == "https://dev.khalti.com/api/v2/epayment/initiate/"
    assert request.headers["Authorization"] == "Key live_secret_key_abc"
    body = json.loads(request.content)
    assert body["amount"] == 1500_00
    assert body["purchase_order_id"] == ORDER.id
    assert body["return_url"] == ORDER.return_url
    assert body["customer_info"] == {"name": "Sita Rai", "phone": "9812345678"}


def test_khalti_refusing_the_key() -> None:
    http, _ = client(lambda r: httpx.Response(401, json={"detail": "Invalid token."}))
    with pytest.raises(KeysRefused):
        Khalti(http).start(KHALTI, ORDER)


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        (200, "Completed", PAID),
        (200, "Pending", PENDING),
        (200, "Initiated", PENDING),
        (400, "Expired", FAILED),
        (400, "User canceled", FAILED),
        (200, "Refunded", FAILED),
    ],
)
def test_khalti_lookup(code: int, status: str, expected: str) -> None:
    http, seen = client(
        lambda r: httpx.Response(
            code,
            json={
                "pidx": "bZQLD9wRVWo4CdESSfuSsB",
                "total_amount": 1500_00,
                "status": status,
                "transaction_id": "GFq9PFS7b2iYvL8Lir9oXe"
                if status == "Completed"
                else None,
                "fee": 0,
                "refunded": False,
            },
        )
    )
    answer = Khalti(http).check(KHALTI, ORDER, {"reference": "bZQLD9wRVWo4CdESSfuSsB"})
    assert answer.status == expected
    if expected == PAID:
        assert (answer.transaction_ref, answer.amount) == (
            "GFq9PFS7b2iYvL8Lir9oXe",
            1500_00,
        )
    assert json.loads(seen[0].content) == {"pidx": "bZQLD9wRVWo4CdESSfuSsB"}
    assert seen[0].url.path == "/api/v2/epayment/lookup/"


# --- Fonepay ---------------------------------------------------------------------

FONEPAY = Keys(
    merchant="fonepay123",
    secret={"secret_key": "fonepay", "username": "bijayk", "password": "password"},
    test=True,
)


def test_fonepay_qr_is_signed_in_its_order() -> None:
    http, seen = client(
        lambda r: httpx.Response(
            201,
            json={
                "message": "successfull",
                "qrMessage": "000201010212...",
                "status": "CREATED",
                "statusCode": 201,
                "success": True,
                "thirdpartyQrWebSocketUrl": "wss://ws.fonepay.com/...",
            },
        )
    )
    checkout = Fonepay(http).start(FONEPAY, ORDER)
    assert (checkout.kind, checkout.qr) == ("qr", "000201010212...")
    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/thirdPartyDynamicQrDownload")
    assert (body["amount"], body["prn"], body["merchantCode"]) == (
        "1500",
        ORDER.id,
        "fonepay123",
    )
    assert body["remarks1"] == "1monthFitnessZone"  # letters and digits only
    message = f"1500,{ORDER.id},fonepay123,{body['remarks1']},{body['remarks2']}"
    assert (
        body["dataValidation"]
        == hmac.new(b"fonepay", message.encode(), hashlib.sha512).hexdigest()
    )
    assert (body["username"], body["password"]) == ("bijayk", "password")


@pytest.mark.parametrize(
    ("status", "expected"),
    [("success", PAID), ("pending", PENDING), ("failed", FAILED)],
)
def test_fonepay_status(status: str, expected: str) -> None:
    http, seen = client(
        lambda r: httpx.Response(
            200,
            json={
                "fonepayTraceId": 7781 if status == "success" else None,
                "merchantCode": "fonepay123",
                "paymentStatus": status,
                "prn": ORDER.id,
            },
        )
    )
    answer = Fonepay(http).check(FONEPAY, ORDER, {})
    assert answer.status == expected
    if expected == PAID:
        assert answer.transaction_ref == "7781"
    body = json.loads(seen[0].content)
    assert (
        body["dataValidation"]
        == hmac.new(
            b"fonepay", f"{ORDER.id},fonepay123".encode(), hashlib.sha512
        ).hexdigest()
    )


# --- the keys, kept ----------------------------------------------------------------


def test_sealed_keys_open_only_for_their_own_row() -> None:
    row, other = uuid.uuid4(), uuid.uuid4()
    box = sealed.seal({"secret_key": "8gBm/:&EnhH.1/q"}, row)
    assert box.startswith("v1:") and "8gBm" not in box
    assert sealed.open_sealed(box, row) == {"secret_key": "8gBm/:&EnhH.1/q"}
    # Copied into another account's row, it doesn't open.
    with pytest.raises(sealed.Unreadable):
        sealed.open_sealed(box, other)
    # Twice the same keys, two different boxes.
    assert sealed.seal({"secret_key": "x"}, row) != sealed.seal(
        {"secret_key": "x"}, row
    )
