"""Sending one Web Push message (PLAN.md §16.3, 8.3).

`console` logs it and is what development and tests use; `webpush` encrypts
it for the browser and signs it with our VAPID key (pywebpush).
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

log = logging.getLogger("gymbhai.push")


class PushError(Exception):
    """The push service failed for now. Retried by the worker."""


class PushGone(PushError):
    """The subscription is no more (404/410): the phone unsubscribed, the app
    was removed, or the browser threw the key away. Never try it again."""


@dataclass
class Target:
    endpoint: str
    p256dh: str
    auth: str


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
        log.info(
            "Push to %s…: %s — %s", target.endpoint[:40], message.title, message.body
        )
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


_console = ConsoleProvider()


def get_provider() -> PushProvider:
    return WebPushProvider() if settings.push_provider == "webpush" else _console
