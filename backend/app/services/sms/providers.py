"""SMS gateways (PLAN.md §3, §15: no provider chosen yet).

One interface; choosing a gateway is SMS_PROVIDER plus its API key. `console`
prints to the log and is what development and tests use.

The Sparrow and Aakash adapters follow those gateways' published HTTP APIs.
Neither has been exercised against a live account yet: check each against the
gateway's current documentation, with a test message, before going live.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings

log = logging.getLogger("gymbhai.sms")


class SmsError(Exception):
    """The gateway refused or failed. Retried by the worker."""


@dataclass
class Sent:
    provider_ref: str | None


class SmsProvider(Protocol):
    name: str

    def send(self, to: str, body: str) -> Sent: ...


class ConsoleProvider:
    """Development: the message goes to the log, nowhere else."""

    name = "console"

    def send(self, to: str, body: str) -> Sent:
        log.info("SMS to %s: %s", to, body)
        return Sent(provider_ref=None)


class SparrowProvider:
    """Sparrow SMS, https://api.sparrowsms.com/v2/sms/."""

    name = "sparrow"
    url = "https://api.sparrowsms.com/v2/sms/"

    def __init__(self, token: str, sender: str, client: httpx.Client | None = None):
        self.token = token
        self.sender = sender
        self.client = client or httpx.Client(timeout=15)

    def send(self, to: str, body: str) -> Sent:
        try:
            response = self.client.post(
                self.url,
                data={"token": self.token, "from": self.sender, "to": to, "text": body},
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SmsError(f"Sparrow unreachable: {exc}") from exc
        if response.status_code != 200 or data.get("response_code") != 200:
            raise SmsError(
                f"Sparrow refused: {data.get('response') or response.text[:200]}"
            )
        return Sent(provider_ref=str(data.get("message_id") or "") or None)


class AakashProvider:
    """Aakash SMS, https://sms.aakashsms.com/sms/v3/send."""

    name = "aakash"
    url = "https://sms.aakashsms.com/sms/v3/send"

    def __init__(self, token: str, client: httpx.Client | None = None):
        self.token = token
        self.client = client or httpx.Client(timeout=15)

    def send(self, to: str, body: str) -> Sent:
        try:
            response = self.client.post(
                self.url, data={"auth_token": self.token, "to": to, "text": body}
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SmsError(f"Aakash unreachable: {exc}") from exc
        valid = (data.get("data") or {}).get("valid") or []
        if response.status_code != 200 or data.get("error") or not valid:
            raise SmsError(
                f"Aakash refused: {data.get('message') or response.text[:200]}"
            )
        return Sent(provider_ref=str(valid[0].get("id") or "") or None)


def get_provider() -> SmsProvider:
    if settings.sms_provider == "sparrow":
        if not settings.sparrow_token:
            raise SmsError("SMS_PROVIDER is sparrow but SPARROW_TOKEN is not set.")
        return SparrowProvider(settings.sparrow_token, settings.sparrow_sender)
    if settings.sms_provider == "aakash":
        if not settings.aakash_token:
            raise SmsError("SMS_PROVIDER is aakash but AAKASH_TOKEN is not set.")
        return AakashProvider(settings.aakash_token)
    return ConsoleProvider()
