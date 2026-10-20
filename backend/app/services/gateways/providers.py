"""The wallets that confirm a member's payment to the gym (PLAN.md §20.2).

Each adapter does two things with the gym's own merchant keys: start a
payment (the page the member's browser is sent to, or the QR it shows), and
check one by asking the wallet itself. What a browser brings back from the
wallet is never trusted: anyone can type a URL.

`console` stands in for all three in development and tests: a pretend
checkout on our own page. eSewa (ePay v2) and Khalti (Web Checkout, KPG-2)
follow their public developer documents (read 2026-10-20). Fonepay gives its
documents to merchants only; its dynamic QR here follows published write-ups
and must be checked against Fonepay's own before a gym turns it on. None of
the three has been called yet, not even their test systems.
"""

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

PAID = "paid"
PENDING = "pending"
FAILED = "failed"


class GatewayError(Exception):
    """The wallet couldn't answer now (network, its servers): try again later."""


class KeysRefused(GatewayError):
    """The wallet refused the gym's keys: the owner must fix them in Settings."""


@dataclass(frozen=True)
class Keys:
    """The gym's merchant account. `secret` is what is kept encrypted."""

    merchant: str | None
    secret: dict[str, str]
    test: bool


@dataclass(frozen=True)
class Order:
    id: str  # ours, sent to the wallet: letters and digits, at most 25
    amount: int  # paisa
    name: str  # what it's for, as the wallet shows it
    return_url: str  # where the wallet sends the member back
    failure_url: str
    website_url: str
    customer_name: str
    customer_phone: str | None


@dataclass
class Checkout:
    """What the member's browser does next: POST `fields` to `url` (a form),
    go to `url` (a redirect), or show `qr`."""

    kind: str
    url: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    qr: str | None = None
    # The wallet's own id for it, when it gives one (Khalti's pidx).
    reference: str | None = None


@dataclass(frozen=True)
class Answer:
    status: str  # paid, pending, failed
    transaction_ref: str | None = None
    # Paisa, as the wallet says; None when it doesn't say.
    amount: int | None = None
    detail: str | None = None


class Gateway(Protocol):
    def start(self, keys: Keys, order: Order) -> Checkout: ...

    def check(self, keys: Keys, order: Order, details: dict[str, Any]) -> Answer: ...


def rupees(paisa: int) -> str:
    """1500 rupees as 1500, 1500.50 as 1500.50: what the wallets expect."""
    whole, cents = divmod(paisa, 100)
    return f"{whole}.{cents:02d}" if cents else str(whole)


def paisa_of(value: Any) -> int | None:
    try:
        return round(float(str(value).replace(",", "")) * 100)
    except (TypeError, ValueError):
        return None


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise GatewayError(f"Not JSON ({response.status_code})") from exc
    if not isinstance(data, dict):
        raise GatewayError(f"Unexpected answer ({response.status_code})")
    return data


# --- eSewa: ePay v2 -----------------------------------------------------------


class Esewa:
    """The member is sent to eSewa with a signed form; eSewa sends them back
    to `success_url` or `failure_url`. The status check is what we believe."""

    FORM = {
        False: "https://epay.esewa.com.np/api/epay/main/v2/form",
        True: "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
    }
    STATUS = {
        False: "https://esewa.com.np/api/epay/transaction/status/",
        True: "https://rc.esewa.com.np/api/epay/transaction/status/",
    }
    SIGNED = "total_amount,transaction_uuid,product_code"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=15)

    @staticmethod
    def signature(secret: str, fields: dict[str, str], names: str) -> str:
        """HMAC-SHA256 of `name=value` for each signed field, in that order,
        joined by commas, as base64."""
        message = ",".join(f"{name}={fields[name]}" for name in names.split(","))
        digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def start(self, keys: Keys, order: Order) -> Checkout:
        amount = rupees(order.amount)
        fields = {
            "amount": amount,
            "tax_amount": "0",
            "total_amount": amount,
            "transaction_uuid": order.id,
            "product_code": keys.merchant or "",
            "product_service_charge": "0",
            "product_delivery_charge": "0",
            "success_url": order.return_url,
            "failure_url": order.failure_url,
            "signed_field_names": self.SIGNED,
        }
        fields["signature"] = self.signature(
            keys.secret["secret_key"], fields, self.SIGNED
        )
        return Checkout(kind="form", url=self.FORM[keys.test], fields=fields)

    def check(self, keys: Keys, order: Order, details: dict[str, Any]) -> Answer:
        try:
            response = self.client.get(
                self.STATUS[keys.test],
                params={
                    "product_code": keys.merchant or "",
                    "total_amount": rupees(order.amount),
                    "transaction_uuid": order.id,
                },
            )
        except httpx.HTTPError as exc:
            raise GatewayError(str(exc)) from exc
        if response.status_code >= 500:
            raise GatewayError(f"eSewa answered {response.status_code}")
        data = _json(response)
        status = str(data.get("status", "")).upper()
        if status == "COMPLETE":
            return Answer(
                PAID,
                transaction_ref=str(data.get("ref_id") or "") or None,
                amount=paisa_of(data.get("total_amount")),
            )
        if status in ("CANCELED", "FULL_REFUND", "PARTIAL_REFUND"):
            return Answer(FAILED, detail=status)
        if response.status_code >= 400 and not status:
            # eSewa's errors carry `error_message`: a wrong merchant code.
            raise KeysRefused(str(data.get("error_message") or response.status_code))
        # PENDING, AMBIGUOUS, NOT_FOUND (not paid, or not yet): ask again later.
        return Answer(PENDING, detail=status or None)


# --- Khalti: Web Checkout (KPG-2) -----------------------------------------------


class Khalti:
    """Khalti gives us a payment page for the order; the member pays there and
    is sent to `return_url`. The lookup is what we believe."""

    BASE = {False: "https://khalti.com/api/v2/", True: "https://dev.khalti.com/api/v2/"}
    FAILED = {"Expired", "User canceled", "Refunded", "Partially Refunded"}

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=15)

    def _post(self, keys: Keys, path: str, body: dict[str, Any]) -> httpx.Response:
        try:
            response = self.client.post(
                self.BASE[keys.test] + path,
                json=body,
                headers={"Authorization": f"Key {keys.secret['secret_key']}"},
            )
        except httpx.HTTPError as exc:
            raise GatewayError(str(exc)) from exc
        if response.status_code in (401, 403):
            raise KeysRefused(f"Khalti refused the key ({response.status_code})")
        if response.status_code >= 500:
            raise GatewayError(f"Khalti answered {response.status_code}")
        return response

    def start(self, keys: Keys, order: Order) -> Checkout:
        customer = {"name": order.customer_name}
        if order.customer_phone and re.fullmatch(r"9\d{9}", order.customer_phone):
            customer["phone"] = order.customer_phone
        response = self._post(
            keys,
            "epayment/initiate/",
            {
                "return_url": order.return_url,
                "website_url": order.website_url,
                "amount": order.amount,
                "purchase_order_id": order.id,
                "purchase_order_name": order.name,
                "customer_info": customer,
            },
        )
        data = _json(response)
        if response.status_code >= 400 or not data.get("payment_url"):
            raise GatewayError(f"Khalti refused the order: {data}")
        return Checkout(
            kind="redirect", url=str(data["payment_url"]), reference=str(data["pidx"])
        )

    def check(self, keys: Keys, order: Order, details: dict[str, Any]) -> Answer:
        pidx = details.get("reference")
        if not pidx:
            return Answer(FAILED, detail="never started")
        response = self._post(keys, "epayment/lookup/", {"pidx": pidx})
        data = _json(response)
        status = str(data.get("status", ""))
        if status == "Completed":
            return Answer(
                PAID,
                transaction_ref=str(data.get("transaction_id") or "") or None,
                amount=int(data["total_amount"])
                if data.get("total_amount") is not None
                else None,
            )
        if status in self.FAILED:
            return Answer(FAILED, detail=status)
        if response.status_code >= 400 and not status:
            raise GatewayError(f"Khalti lookup failed: {data}")
        # Initiated (not paid yet) or Pending (Khalti is still sure of nothing).
        return Answer(PENDING, detail=status or None)


# --- Fonepay: dynamic QR ----------------------------------------------------------


class Fonepay:
    """A QR for exactly this amount, which any Nepali bank app can pay; its
    status says when it has been. To be checked against Fonepay's own
    documents with a merchant account (module docstring)."""

    BASE = {
        False: "https://merchantapi.fonepay.com/api",
        True: "https://dev-merchantapi.fonepay.com/api",
    }
    QR = "/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrDownload"
    STATUS = "/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrGetStatus"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=15)

    @staticmethod
    def validation(secret: str, *values: str) -> str:
        """HMAC-SHA512 of the values joined by commas, as lowercase hex."""
        message = ",".join(values).encode()
        return hmac.new(secret.encode(), message, hashlib.sha512).hexdigest()

    @staticmethod
    def remark(text: str) -> str:
        # Letters and digits only, at most 25.
        return re.sub(r"[^A-Za-z0-9]", "", text)[:25] or "GymBhai"

    def _post(self, keys: Keys, path: str, body: dict[str, Any]) -> dict[str, Any]:
        body = {
            **body,
            "username": keys.secret.get("username", ""),
            "password": keys.secret.get("password", ""),
        }
        try:
            response = self.client.post(self.BASE[keys.test] + path, json=body)
        except httpx.HTTPError as exc:
            raise GatewayError(str(exc)) from exc
        if response.status_code >= 500:
            raise GatewayError(f"Fonepay answered {response.status_code}")
        data = _json(response)
        if response.status_code in (401, 403) or (
            response.status_code >= 400 and "credential" in str(data).lower()
        ):
            raise KeysRefused(str(data.get("message") or response.status_code))
        if response.status_code >= 400:
            raise GatewayError(str(data.get("message") or response.status_code))
        return data

    def start(self, keys: Keys, order: Order) -> Checkout:
        merchant = keys.merchant or ""
        amount = rupees(order.amount)
        remarks1, remarks2 = self.remark(order.name), self.remark("GymBhai")
        data = self._post(
            keys,
            self.QR,
            {
                "amount": amount,
                "remarks1": remarks1,
                "remarks2": remarks2,
                "prn": order.id,
                "merchantCode": merchant,
                "dataValidation": self.validation(
                    keys.secret["secret_key"],
                    amount,
                    order.id,
                    merchant,
                    remarks1,
                    remarks2,
                ),
            },
        )
        if not data.get("success") or not data.get("qrMessage"):
            raise GatewayError(str(data.get("message") or "no QR"))
        return Checkout(kind="qr", qr=str(data["qrMessage"]))

    def check(self, keys: Keys, order: Order, details: dict[str, Any]) -> Answer:
        merchant = keys.merchant or ""
        data = self._post(
            keys,
            self.STATUS,
            {
                "prn": order.id,
                "merchantCode": merchant,
                "dataValidation": self.validation(
                    keys.secret["secret_key"], order.id, merchant
                ),
            },
        )
        status = str(data.get("paymentStatus", "")).lower()
        if status == "success":
            trace = data.get("fonepayTraceId")
            return Answer(PAID, transaction_ref=str(trace) if trace else None)
        if status == "failed":
            return Answer(FAILED, detail=status)
        return Answer(PENDING, detail=status or None)


# --- console ---------------------------------------------------------------------


class Console:
    """A pretend wallet on our own page, for development and tests: *Pay*
    or *Cancel* there sets its answer, which `check` then reads."""

    def start(self, keys: Keys, order: Order) -> Checkout:
        return Checkout(kind="console")

    def check(self, keys: Keys, order: Order, details: dict[str, Any]) -> Answer:
        answer = details.get("console")
        if answer == PAID:
            return Answer(PAID, transaction_ref=f"TEST{order.id[:12].upper()}")
        if answer == FAILED:
            return Answer(FAILED, detail="cancelled")
        return Answer(PENDING)


WALLETS = ("esewa", "khalti", "fonepay")


def gateway(kind: str, provider: str) -> Gateway:
    """The adapter for a wallet, or the console one in development."""
    if provider == "console":
        return Console()
    return {"esewa": Esewa, "khalti": Khalti, "fonepay": Fonepay}[kind]()
