"""The phone app's WebSocket (PLAN.md §17.3): auth by message, the member's
own events only, pings, a fresh token on the same socket, and closing when
the token runs out or the app goes quiet."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.api.routes import member_socket
from app.core.time import utcnow
from app.models.member_app import MemberSession
from app.services import live, member_auth
from tests.conftest import GymFixture, make_member

URL = "/api/v1/m/ws"


class TestHub(live.Hub):
    """No Postgres: the test hands events in from its own thread."""

    __test__ = False

    def __init__(self) -> None:
        super().__init__("postgresql://unused")
        self.loop: asyncio.AbstractEventLoop | None = None

    async def subscribe(self, accepts):
        self.loop = asyncio.get_running_loop()
        return await super().subscribe(accepts)

    async def _listen(self) -> None:
        await asyncio.Event().wait()

    def send(self, event: dict) -> None:
        assert self.loop is not None, "nobody subscribed"
        self.loop.call_soon_threadsafe(self.dispatch, event)


@pytest.fixture
def hub(monkeypatch) -> TestHub:
    fake = TestHub()
    monkeypatch.setattr(live, "hub", fake)
    return fake


def token_for(db: Session, member) -> str:
    issued = member_auth.start_session(db, member, None, "app")
    db.commit()
    return issued.access_token


def event(kind: str, gym, member=None, branch=None) -> dict:
    return {
        "type": kind,
        "gym": str(gym),
        "member": str(member) if member else None,
        "branch": str(branch) if branch else None,
    }


def closed_with(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as caught:
        ws.receive_json()
    return caught.value.code


def test_events_reach_only_the_member_they_are_about(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub
) -> None:
    member = make_member(db, gym_a)
    other = make_member(db, gym_a, phone="9800000502", name="Gita")
    gym, branch = gym_a.gym.id, gym_a.branch.id
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": token_for(db, member)})
        assert ws.receive_json() == {"type": "ready"}
        hub.send(event(live.CHECK_IN, gym, member=other.id))  # not theirs
        hub.send(event(live.NOTICE, uuid.uuid4()))  # another gym's notice
        hub.send(event(live.NOTICE, gym, branch=uuid.uuid4()))  # another branch's
        hub.send(event(live.PAYMENT_REQUEST, gym, member=member.id))
        hub.send(event(live.NOTICE, gym))  # every branch
        hub.send(event(live.NOTICE, gym, branch=branch))  # their branch
        hub.send({"type": live.RESYNC})  # everyone
        got = [ws.receive_json() for _ in range(4)]
    assert [e["type"] for e in got] == [
        live.PAYMENT_REQUEST,
        live.NOTICE,
        live.NOTICE,
        live.RESYNC,
    ]
    assert got[0]["member"] == str(member.id)
    assert not hub.subscribers, "a closed socket must unsubscribe"


@pytest.mark.parametrize(
    "first",
    [
        {"type": "auth", "token": "not-a-token"},
        {"type": "auth"},
        {"type": "hello"},
        ["auth"],
    ],
)
def test_no_valid_token_first_is_closed(
    client: TestClient, hub: TestHub, first
) -> None:
    with client.websocket_connect(URL) as ws:
        ws.send_json(first)
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED
    assert not hub.subscribers


def test_silence_before_auth_is_closed(
    client: TestClient, hub: TestHub, monkeypatch
) -> None:
    monkeypatch.setattr(member_socket, "AUTH_SECONDS", 0.2)
    with client.websocket_connect(URL) as ws:
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED


def test_a_staff_token_is_not_a_members(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub
) -> None:
    from tests.conftest import sign_in

    staff_token = sign_in(db, client, gym_a.owner)
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": staff_token})
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED


def test_a_signed_out_session_cannot_connect(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub
) -> None:
    member = make_member(db, gym_a)
    token = token_for(db, member)
    for row in db.query(MemberSession).filter_by(member_id=member.id):
        row.revoked_at = utcnow()
    db.commit()
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED


def test_pings_and_going_quiet(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub, monkeypatch
) -> None:
    monkeypatch.setattr(member_socket, "PING_SECONDS", 0.1)
    monkeypatch.setattr(member_socket, "SILENT_SECONDS", 0.5)
    member = make_member(db, gym_a)
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": token_for(db, member)})
        assert ws.receive_json() == {"type": "ready"}
        # Answering keeps it open past SILENT_SECONDS...
        for _ in range(8):
            assert ws.receive_json() == {"type": "ping"}
            ws.send_json({"type": "pong"})
        # ...and not answering closes it.
        code = None
        while code is None:
            try:
                assert ws.receive_json() == {"type": "ping"}
            except WebSocketDisconnect as closed:
                code = closed.code
    assert code == member_socket.CLOSE_SILENT


def test_a_fresh_token_keeps_it_open_and_expiry_closes_it(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub, monkeypatch
) -> None:
    # Every token "expires" a moment after it is checked.
    real = member_socket._check

    def short(db, token, loop):
        who = real(db, token, loop)
        if who is not None:
            who.expires_at = loop.time() + 0.6
        return who

    monkeypatch.setattr(member_socket, "_check", short)
    member = make_member(db, gym_a)
    # Made first: the test shares one database session with the socket.
    first, fresh = token_for(db, member), token_for(db, member)
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": first})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "auth", "token": fresh})
        hub.send(event(live.MEMBER, gym_a.gym.id, member=member.id))
        assert ws.receive_json()["type"] == live.MEMBER  # still open
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED


def test_a_message_that_is_not_json_closes_it(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub
) -> None:
    token = token_for(db, make_member(db, gym_a))
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text("{not json")
        assert closed_with(ws) == member_socket.CLOSE_ERROR
    assert not hub.subscribers


def test_another_members_token_on_the_same_socket_closes_it(
    client: TestClient, db: Session, gym_a: GymFixture, hub: TestHub
) -> None:
    member = make_member(db, gym_a)
    other = make_member(db, gym_a, phone="9800000503", name="Gita")
    mine, theirs = token_for(db, member), token_for(db, other)
    with client.websocket_connect(URL) as ws:
        ws.send_json({"type": "auth", "token": mine})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "auth", "token": theirs})
        assert closed_with(ws) == member_socket.CLOSE_UNAUTHORIZED
