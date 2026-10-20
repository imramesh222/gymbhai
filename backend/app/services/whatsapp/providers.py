"""Sending WhatsApp messages (PLAN.md §19.3): one interface, as SMS has.

`console` logs what would be sent; development and tests use it. `meta` is
Meta's WhatsApp Cloud API, called directly with our System User's token.

The Meta adapter follows the Cloud API's published reference (messages and
error codes, read 2026-10-20). It hasn't sent a real message yet: GymBhai's
Meta business, number and templates are still waiting for approval.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings

log = logging.getLogger("gymbhai.whatsapp")

GRAPH = "https://graph.facebook.com"


class WhatsAppError(Exception):
    """Meta failed for now (network, its servers, a rate limit): retried."""


class WhatsAppRejected(WhatsAppError):
    """Meta refused this message itself: sending it again won't help, so the
    SMS goes instead."""


class NotOnWhatsApp(WhatsAppRejected):
    """The number isn't on WhatsApp (or can't take business messages)."""


# Meta's error codes (Cloud API reference, "Error codes"). Unlisted ones are
# refusals: the SMS goes at once rather than after half an hour of retries.
NOT_ON_WHATSAPP = {131026}
TRANSIENT = {
    1,  # API unknown
    2,  # API service: temporary downtime or overload
    4,  # too many calls for the app
    80007,  # the business account's rate limit
    130429,  # throughput reached
    131000,  # something went wrong
    131016,  # service overloaded
    131056,  # too many messages to one number at once
    133004,  # server temporarily unavailable
}


@dataclass
class Outgoing:
    to: str  # 98XXXXXXXX
    template: str
    language: str  # Meta's code
    values: list[str]
    button: str | None = None


@dataclass
class Sent:
    provider_ref: str | None


class WhatsAppProvider(Protocol):
    name: str

    def send_template(self, message: Outgoing) -> Sent: ...

    def send_text(self, to: str, body: str) -> Sent: ...


def international(phone: str) -> str:
    """WhatsApp wants the country code and no plus: 9779812345678."""
    return phone if phone.startswith("977") else f"977{phone}"


def template_payload(message: Outgoing) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    if message.values:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in message.values],
            }
        )
    if message.button:
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": message.button}],
            }
        )
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": international(message.to),
        "type": "template",
        "template": {
            "name": message.template,
            "language": {"code": message.language},
            "components": components,
        },
    }


class ConsoleProvider:
    """Development: the message goes to the log, nowhere else."""

    name = "console"

    def send_template(self, message: Outgoing) -> Sent:
        log.info(
            "WhatsApp to %s: %s (%s) %s %s",
            message.to,
            message.template,
            message.language,
            message.values,
            message.button or "",
        )
        return Sent(provider_ref=f"console.{uuid.uuid4().hex}")

    def send_text(self, to: str, body: str) -> Sent:
        log.info("WhatsApp reply to %s: %s", to, body)
        return Sent(provider_ref=f"console.{uuid.uuid4().hex}")


class MetaProvider:
    """Meta's WhatsApp Cloud API, POST /<version>/<phone number id>/messages."""

    name = "meta"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        version: str,
        client: httpx.Client | None = None,
    ):
        self.token = token
        self.url = f"{GRAPH}/{version}/{phone_number_id}/messages"
        self.client = client or httpx.Client(timeout=15)

    def send_template(self, message: Outgoing) -> Sent:
        return self._post(template_payload(message))

    def send_text(self, to: str, body: str) -> Sent:
        return self._post(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": international(to),
                "type": "text",
                "text": {"body": body, "preview_url": True},
            }
        )

    def _post(self, payload: dict[str, Any]) -> Sent:
        try:
            response = self.client.post(
                self.url,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WhatsAppError(f"Meta unreachable: {exc}") from exc
        if response.status_code == 200 and data.get("messages"):
            return Sent(provider_ref=str(data["messages"][0].get("id") or "") or None)
        raise failure(response.status_code, data.get("error") or {})


def failure(status: int, error: dict[str, Any]) -> WhatsAppError:
    """The exception for one of Meta's errors, in a send's answer or a
    delivery report."""
    code = error.get("code")
    details = (error.get("error_data") or {}).get("details")
    said = f"Meta refused ({code}): {error.get('message') or error.get('title')}"
    if details:
        said += f" ({details})"
    if code in NOT_ON_WHATSAPP:
        return NotOnWhatsApp(said)
    if code in TRANSIENT or status >= 500:
        return WhatsAppError(said)
    log.error("WhatsApp: %s", said)
    return WhatsAppRejected(said)


def get_provider() -> WhatsAppProvider:
    if settings.whatsapp_provider == "meta":
        assert settings.whatsapp_token and settings.whatsapp_phone_number_id
        return MetaProvider(
            settings.whatsapp_token,
            settings.whatsapp_phone_number_id,
            settings.whatsapp_api_version,
        )
    return ConsoleProvider()
