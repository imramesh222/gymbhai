"""Saving a payment once, however many times the request arrives (§16.1).

A desk on weak mobile data taps Save; the request reaches us but the answer
is lost on the way back; they tap again. Without this, that is two payments.

The browser sends an `Idempotency-Key` header, made once for each thing being
saved and kept until it gets an answer (frontend/src/lib/idempotency.ts). A
money route calls `begin()` first and `finish()` just before it commits, so
the answer is saved in the same transaction as the payment:

* same key, same request      -> the first answer again, nothing changes
                                 (`Idempotent-Replayed: true`)
* same key, different request -> 409 `idempotency_key_reused`
* same key, first still running -> waits on the unique index, then the first
                                 answer
* the first one failed        -> nothing was saved, key included (its
                                 transaction rolled back): it runs again

Without the header a request runs as it always did: scripts and tests.
"""

import hashlib
import re
from dataclasses import dataclass

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tenancy import StaffContext
from app.core.errors import AppError
from app.models.idempotency import IdempotencyKey

HEADER = "Idempotency-Key"
_VALID_KEY = re.compile(r"^[A-Za-z0-9_-]{8,100}$")


class Replay(Exception):
    """The request was already done: send its answer again."""

    def __init__(self, status_code: int, body: object) -> None:
        super().__init__("replayed")
        self.status_code = status_code
        self.body = body


def replay_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, Replay)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.body,
        headers={"Idempotent-Replayed": "true"},
    )


@dataclass
class Idempotency:
    row: IdempotencyKey | None
    status_code: int

    def finish(self, answer: BaseModel) -> None:
        """Keep the answer, in the transaction about to be committed."""
        if self.row is not None:
            self.row.status_code = self.status_code
            self.row.response = jsonable_encoder(answer)


def _replay_or_refuse(row: IdempotencyKey, route: str, request_hash: str) -> Replay:
    if row.route != route or row.request_hash != request_hash:
        raise AppError(
            409,
            "idempotency_key_reused",
            "That key was already used for a different request.",
        )
    if row.status_code is None:
        # A key committed without its answer: a route that forgot finish().
        raise AppError(409, "already_done", "This was already saved. Refresh.")
    return Replay(row.status_code, row.response)


def begin(
    db: Session, ctx: StaffContext, request: Request, payload: BaseModel
) -> Idempotency:
    """Claim the request's key, or raise Replay with the answer already given."""
    route_obj = request.scope.get("route")
    status_code = getattr(route_obj, "status_code", None) or 200
    key = request.headers.get(HEADER)
    if key is None:
        return Idempotency(None, status_code)
    if not _VALID_KEY.match(key):
        raise AppError(422, "bad_idempotency_key", "Invalid Idempotency-Key header.")

    route = f"{request.method} {request.url.path}"[:200]
    request_hash = hashlib.sha256(
        f"{route}\n{payload.model_dump_json()}".encode()
    ).hexdigest()

    def existing() -> IdempotencyKey | None:
        return db.scalars(
            select(IdempotencyKey).where(
                IdempotencyKey.gym_id == ctx.gym_id, IdempotencyKey.key == key
            )
        ).first()

    found = existing()
    if found is not None:
        raise _replay_or_refuse(found, route, request_hash)
    row = IdempotencyKey(
        gym_id=ctx.gym_id, key=key, route=route, request_hash=request_hash
    )
    try:
        # A savepoint: if the same key is being saved right now, this waits on
        # the unique index until that transaction ends.
        with db.begin_nested():
            db.add(row)
    except IntegrityError:
        found = existing()
        if found is None:
            raise
        raise _replay_or_refuse(found, route, request_hash) from None
    return Idempotency(row, status_code)
