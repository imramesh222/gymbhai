"""SMS gateways (PLAN.md §3, §15: no provider chosen yet).

One interface; choosing a gateway is SMS_PROVIDER plus its API key. `console`
prints to the log and is what development and tests use.

The Sparrow adapter follows docs.sparrowsms.com (v2, read 2026-09-20); the
Aakash one that gateway's published API. Neither has been exercised against a
live account yet: send a test message before trusting either.
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings

log = logging.getLogger("gymbhai.sms")


class SmsError(Exception):
    """The gateway refused or failed. Retried by the worker."""


class SmsRejected(SmsError):
    """The gateway refused this message itself; sending it again won't help."""


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
    """Sparrow SMS, https://api.sparrowsms.com/v2/."""

    name = "sparrow"
    url = "https://api.sparrowsms.com/v2/sms/"
    credit_url = "https://api.sparrowsms.com/v2/credit/"

    # Answers about this request rather than about this moment: the same
    # message sent again gets the same answer, so it fails now instead of
    # after four more attempts. The rest (account inactive or expired, out of
    # credit) can be put right while the job backs off, so those are retried.
    PERMANENT = {
        1000,  # a required field is missing
        1001,  # invalid IP address (our server is not whitelisted)
        1002,  # invalid token
        1007,  # invalid receiver
        1008,  # invalid sender
        1010,  # text cannot be empty
        1011,  # no valid receiver
    }

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
        self._check(response, data)
        # Sparrow answers {"count", "response_code", "response"}: the message is
        # queued, and nothing identifies it. Delivery reports are a separate
        # service, so there is no reference to keep.
        return Sent(provider_ref=None)

    def credits(self) -> int:
        """SMS credits left on our Sparrow account (not a gym's balance)."""
        try:
            response = self.client.get(self.credit_url, params={"token": self.token})
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SmsError(f"Sparrow unreachable: {exc}") from exc
        self._check(response, data)
        return int(float(data.get("credits_available") or 0))

    def _check(self, response: httpx.Response, data: dict[str, Any]) -> None:
        """Sparrow reports failure in the body, sometimes with a 200 status."""
        code = data.get("response_code")
        if response.status_code == 200 and code == 200:
            return
        said = data.get("response") or response.text[:200]
        failure = SmsRejected if code in self.PERMANENT else SmsError
        raise failure(f"Sparrow refused ({code}): {said}")


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
