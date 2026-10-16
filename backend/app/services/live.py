"""Live updates: screens that change when something happens elsewhere.

* A member scans in at the door      -> Today, Attendance, the member's app
* A member sends "I've paid"         -> the Payment requests badge and list
* Staff approve or reject it         -> the member's app, other approvers
* A sale, payment, freeze, edit, ... -> the member's page and their app

How: the change calls `publish()` in its own transaction. That is a Postgres
NOTIFY, delivered only if the transaction commits, so nobody hears about a
change that was rolled back. Every API process LISTENs on one connection and
passes each event to the streams open on it that may see it (same gym, the
right permission and branch, or the member themselves).

Events carry ids, never data: a screen that hears one reloads through the
normal API, which checks permissions as it always does.

Streams are Server-Sent Events rather than WebSockets: the traffic is one way,
and an ordinary GET passes through the Next.js /api proxy and Caddy with the
usual Authorization header.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings

if TYPE_CHECKING:
    from app.api.tenancy import StaffContext

log = logging.getLogger("gymbhai.live")

CHANNEL = "gymbhai_live"

CHECK_IN = "check_in"
PAYMENT_REQUEST = "payment_request"
MEMBER = "member"
# Sent by us, not by a change: events may have been missed (the listener lost
# its connection), so reload everything on screen.
RESYNC = "resync"

# A comment line this often keeps proxies from closing a quiet stream.
HEARTBEAT_SECONDS = 25
# Events waiting for a slow client beyond this are dropped; it gets a resync.
QUEUE_SIZE = 100

Event = dict[str, Any]


def publish(
    db: Session,
    *,
    gym_id: uuid.UUID,
    kind: str,
    member_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> None:
    """Tell open screens, once (and only if) this transaction commits."""
    payload = {
        "type": kind,
        "gym": str(gym_id),
        "member": str(member_id) if member_id else None,
        "branch": str(branch_id) if branch_id else None,
    }
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": json.dumps(payload)},
    )


def member_changed(
    db: Session, gym_id: uuid.UUID, member_id: uuid.UUID, branch_id: uuid.UUID
) -> None:
    publish(db, gym_id=gym_id, kind=MEMBER, member_id=member_id, branch_id=branch_id)


# --- who sees what ------------------------------------------------------------------


def staff_filter(ctx: "StaffContext") -> Callable[[Event], bool]:
    """Staff hear about their own gym only, and only what they could open."""
    from app.core.permissions import Permission

    gym = str(ctx.gym_id)
    branches = None if ctx.branch_ids is None else {str(b) for b in ctx.branch_ids}
    sees_members = ctx.can(Permission.MEMBERS_VIEW)
    approves = ctx.can(Permission.PAYMENTS_APPROVE_APP)

    def accepts(event: Event) -> bool:
        if event.get("gym") != gym:
            return False
        if event["type"] == PAYMENT_REQUEST:
            return approves
        if event["type"] in (CHECK_IN, MEMBER):
            return sees_members and (
                branches is None or event.get("branch") in branches
            )
        return False

    return accepts


def member_filter(member_id: uuid.UUID) -> Callable[[Event], bool]:
    """A member hears only about themselves."""
    me = str(member_id)
    return lambda event: event.get("member") == me


# --- one listener per process, many streams --------------------------------------


@dataclass(eq=False)
class Subscriber:
    accepts: Callable[[Event], bool]
    queue: asyncio.Queue[Event] = field(
        default_factory=lambda: asyncio.Queue(QUEUE_SIZE)
    )


def _psycopg_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(False)


class Hub:
    """LISTENs once for the whole process, started by the first stream."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.subscribers: set[Subscriber] = set()
        self.connected = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def subscribe(self, accepts: Callable[[Event], bool]) -> Subscriber:
        subscriber = Subscriber(accepts)
        self.subscribers.add(subscriber)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen())
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self.subscribers.discard(subscriber)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.connected.clear()

    def dispatch(self, event: Event) -> None:
        for subscriber in list(self.subscribers):
            if event["type"] != RESYNC and not subscriber.accepts(event):
                continue
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Too far behind to catch up event by event: start over.
                while not subscriber.queue.empty():
                    subscriber.queue.get_nowait()
                subscriber.queue.put_nowait({"type": RESYNC})

    async def _listen(self) -> None:
        import psycopg

        delay = 1.0
        first = True
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    _psycopg_url(self.database_url), autocommit=True
                ) as connection:
                    await connection.execute(f"LISTEN {CHANNEL}")
                    self.connected.set()
                    if not first:
                        self.dispatch({"type": RESYNC})
                    first, delay = False, 1.0
                    async for notify in connection.notifies():
                        try:
                            self.dispatch(json.loads(notify.payload))
                        except (ValueError, KeyError):
                            log.warning("bad live event: %r", notify.payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("live listener lost its connection; retrying")
            self.connected.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


hub = Hub(settings.database_url)


async def stream(
    accepts: Callable[[Event], bool], *, seconds: float, source: Hub | None = None
) -> AsyncIterator[str]:
    """The event stream for one screen, as Server-Sent Events.

    It ends after `seconds` (the access token's lifetime): the browser then
    reconnects with a fresh token, so a revoked session or a removed
    permission stops receiving events within that time.
    """
    source = source or hub
    subscriber = await source.subscribe(accepts)
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + seconds
    try:
        yield "retry: 3000\n\n"
        while (left := ends_at - loop.time()) > 0:
            try:
                event = await asyncio.wait_for(
                    subscriber.queue.get(), min(left, HEARTBEAT_SECONDS)
                )
            except TimeoutError:
                if ends_at > loop.time():
                    yield ": ping\n\n"
                continue
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
    finally:
        source.unsubscribe(subscriber)


STREAM_HEADERS = {
    # no-transform: the Next.js dev proxy would otherwise gzip and buffer it.
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}
