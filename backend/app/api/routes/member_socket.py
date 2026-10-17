"""The phone app's live updates over a WebSocket (PLAN.md §17.3).

    wss://<domain>/api/v1/m/ws

1. The app's first message is {"type": "auth", "token": "<access token>"},
   within AUTH_SECONDS, or the socket closes with 4401. A token never goes in
   the URL, so it never reaches a log.
2. The server answers {"type": "ready"}, then sends events as they happen:
   {"type": "member" | "payment_request" | "freeze_request" | "check_in" |
   "notice" | "resync", ...ids}. Events carry ids, never data: the app re-reads
   through the normal API, which checks permissions as always.
3. Before its token expires the app sends a fresh one, {"type": "auth", ...},
   on the same socket. A token that expires without one closes it with 4401;
   the app refreshes and reconnects. So a revoked session stops hearing within
   one token's lifetime, as with the web's streams.
4. Every PING_SECONDS the server sends {"type": "ping"}; the app answers
   {"type": "pong"}. Nothing heard for SILENT_SECONDS: closed with 4408.

The same event hub as the web's Server-Sent Events (app/services/live.py),
with the same member filter: a member hears about themselves and their gym's
notices, nothing else.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import member_for_token
from app.core.errors import AppError
from app.core.time import utcnow
from app.db.session import get_db
from app.services import live

log = logging.getLogger("gymbhai.live")

router = APIRouter(prefix="/m", tags=["member app"])

AUTH_SECONDS = 5.0
PING_SECONDS = 25.0
SILENT_SECONDS = 60.0

CLOSE_UNAUTHORIZED = 4401
CLOSE_SILENT = 4408
# Our fault, or a message that wasn't JSON: the app reconnects.
CLOSE_ERROR = 1011


@dataclass
class Who:
    member_id: uuid.UUID
    gym_id: uuid.UUID
    branch_id: uuid.UUID
    expires_at: float  # the token's end, as loop time


def _check(db: Session, token: object, loop: asyncio.AbstractEventLoop) -> Who | None:
    """Who the token belongs to, or None. Runs off the event loop."""
    if not isinstance(token, str) or not token:
        return None
    try:
        member, claims = member_for_token(db, token)
    except AppError:
        return None
    finally:
        # Ends the transaction, so the connection goes back to the pool
        # instead of being held for the life of the socket.
        db.rollback()
    expires = claims.expires_at or utcnow()
    return Who(
        member_id=member.id,
        gym_id=member.gym_id,
        branch_id=member.home_branch_id,
        expires_at=loop.time() + (expires - utcnow()).total_seconds(),
    )


@router.websocket("/ws")
async def member_socket(websocket: WebSocket) -> None:
    # The session only checks tokens, holding no connection in between.
    db_gen = get_db_override(websocket)
    db = next(db_gen)
    loop = asyncio.get_running_loop()
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_SECONDS)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return
    who = (
        await run_in_threadpool(_check, db, first.get("token"), loop)
        if isinstance(first, dict) and first.get("type") == "auth"
        else None
    )
    if who is None:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return

    subscriber = await live.hub.subscribe(
        live.member_filter(who.member_id, who.gym_id, who.branch_id)
    )
    heard = loop.time()
    closing: int | None = None

    async def receive() -> None:
        nonlocal who, heard, closing
        while True:
            message = await websocket.receive_json()
            heard = loop.time()
            if not isinstance(message, dict):
                continue
            if message.get("type") == "auth":
                renewed = await run_in_threadpool(
                    _check, db, message.get("token"), loop
                )
                if renewed is None or renewed.member_id != who.member_id:
                    closing = CLOSE_UNAUTHORIZED
                    return
                who = renewed

    reader = asyncio.create_task(receive())
    try:
        await websocket.send_json({"type": "ready"})
        next_ping = loop.time() + PING_SECONDS
        while not reader.done():
            now = loop.time()
            if now >= who.expires_at:
                closing = CLOSE_UNAUTHORIZED
                break
            if now - heard >= SILENT_SECONDS:
                closing = CLOSE_SILENT
                break
            if now >= next_ping:
                await websocket.send_json({"type": "ping"})
                next_ping = now + PING_SECONDS
            wait = max(0.05, min(next_ping, who.expires_at) - loop.time())
            getter = asyncio.ensure_future(subscriber.queue.get())
            done, _ = await asyncio.wait(
                {getter, reader}, timeout=wait, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                await websocket.send_json(getter.result())
            else:
                getter.cancel()
        if reader.done() and closing is None:
            error = reader.exception()
            if error is None or isinstance(error, WebSocketDisconnect):
                return  # the app went away
            if not isinstance(error, ValueError):  # unreadable JSON is theirs
                log.error("member socket failed", exc_info=error)
            closing = CLOSE_ERROR
    except WebSocketDisconnect:
        return
    finally:
        live.hub.unsubscribe(subscriber)
        reader.cancel()
        with contextlib.suppress(Exception):
            db_gen.close()
    await _close(websocket, closing or CLOSE_UNAUTHORIZED)


async def _close(websocket: WebSocket, code: int) -> None:
    with contextlib.suppress(Exception):
        await websocket.close(code=code)


def get_db_override(websocket: WebSocket):
    """The request's database session, honouring the tests' override of
    get_db (a websocket route can't take Depends(get_db) and close it early)."""
    provider = websocket.app.dependency_overrides.get(get_db, get_db)
    return provider()
