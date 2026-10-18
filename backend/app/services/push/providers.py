"""Sending push messages (PLAN.md §16.3, 8.3; §17.6).

`console` logs them and is what development and tests use. Otherwise a
browser subscription goes by Web Push, encrypted and signed with our VAPID key
(pywebpush), and the phone app's token goes to Expo's push service, which
hands it to Apple or Google.
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings

log = logging.getLogger("gymbhai.push")


class PushError(Exception):
    """The push service failed for now. Retried by the worker."""


class PushGone(PushError):
    """The subscription is no more (404/410): the phone unsubscribed, the app
    was removed, or the browser threw the key away. Never try it again."""


@dataclass
class Target:
    """A browser (endpoint and keys) or the phone app (expo_token)."""

    endpoint: str | None = None
    p256dh: str | None = None
    auth: str | None = None
    expo_token: str | None = None

    @property
    def is_expo(self) -> bool:
        return self.expo_token is not None


@dataclass
class PushMessage:
    title: str
    body: str
    # Where tapping the notification opens, inside the member app.
    url: str
    # Same tag, same notification: a newer one replaces it instead of piling up.
    tag: str | None = None


class PushProvider(Protocol):
    name: str

    def send(self, target: Target, message: PushMessage) -> None: ...


class ConsoleProvider:
    """Development and tests: logged, and kept in `sent` for tests to read."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[Target, PushMessage]] = []

    def send(self, target: Target, message: PushMessage) -> None:
        to = target.expo_token or target.endpoint or ""
        log.info("Push to %s…: %s — %s", to[:40], message.title, message.body)
        self.sent.append((target, message))


class WebPushProvider:
    name = "webpush"

    def send(self, target: Target, message: PushMessage) -> None:
        from pywebpush import WebPushException, webpush
        from requests import RequestException

        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(message.__dict__),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                # A reminder a day late is still worth having; older, not.
                ttl=24 * 60 * 60,
                timeout=10,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                raise PushGone(str(exc)) from exc
            raise PushError(str(exc)) from exc
        except RequestException as exc:  # no answer at all: try again later
            raise PushError(str(exc)) from exc


class ExpoProvider:
    """The phone app (§17.6): one message to Expo's push service.

    Expo answers each message with a "ticket"; DeviceNotRegistered there means
    the app was removed or its token replaced. The later "receipts" can say
    the same, but a gone token also fails the next send, so tickets suffice.
    """

    name = "expo"
    URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def send(self, target: Target, message: PushMessage) -> None:
        headers = {"accept": "application/json"}
        if settings.expo_access_token:
            headers["authorization"] = f"Bearer {settings.expo_access_token}"
        body = {
            "to": target.expo_token,
            "title": message.title,
            "body": message.body,
            # The app opens this screen when the notification is tapped.
            "data": {"url": message.url, "tag": message.tag},
            "sound": "default",
            # Android: the app's own "GymBhai" channel (mobile/src/lib/push.tsx),
            # not Expo's fallback, so members see the right name in settings.
            "channelId": "default",
            "priority": "high",
            "ttl": 24 * 60 * 60,
        }
        if message.tag:
            body["collapseId"] = message.tag  # Android: replaces, as on the web
        try:
            client = self.client or httpx.Client(timeout=10)
            try:
                response = client.post(self.URL, json=body, headers=headers)
            finally:
                if self.client is None:
                    client.close()
        except httpx.HTTPError as exc:  # no answer at all: try again later
            raise PushError(str(exc)) from exc
        if response.status_code >= 400:
            raise PushError(f"Expo answered {response.status_code}")
        try:
            ticket = response.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PushError("Expo's answer was unreadable") from exc
        if isinstance(ticket, list):
            ticket = ticket[0] if ticket else {}
        if ticket.get("status") == "ok":
            return
        error = (ticket.get("details") or {}).get("error")
        if error == "DeviceNotRegistered":
            raise PushGone(ticket.get("message") or error)
        raise PushError(ticket.get("message") or error or "Expo refused it")


_console = ConsoleProvider()


def get_provider(target: Target | None = None) -> PushProvider:
    """Console in development and tests; else Web Push or Expo by the target."""
    if settings.push_provider == "console":
        return _console
    if target is not None and target.is_expo:
        return ExpoProvider()
    return WebPushProvider()
