"""A member's signed-in devices (PLAN.md §17.5): listed, signed out one by
one or all but this one, and a signed-out phone's notifications stop."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.member_app import MemberSession
from app.models.push import PushSubscription
from app.services import member_auth
from tests.conftest import GymFixture, make_member, sign_in

EXPO = "ExponentPushToken[abcdefghij{:010d}]"


def signed_in(db: Session, client: TestClient, member, client_kind="web"):
    """A new session for `member`, and a client that uses it."""
    issued = member_auth.start_session(db, member, None, client_kind)
    issued.session.device_label = f"{client_kind} phone"
    db.commit()
    phone = TestClient(client.app)
    phone.headers["Authorization"] = f"Bearer {issued.access_token}"
    return phone, issued.session


def push_on(phone: TestClient, n: int) -> None:
    body = {"kind": "expo", "expo_token": EXPO.format(n)}
    assert phone.post("/api/v1/m/me/push", json=body).status_code == 200


def live_push(db: Session, member) -> set[str]:
    return set(
        db.scalars(
            select(PushSubscription.expo_token).where(
                PushSubscription.member_id == member.id,
                PushSubscription.revoked_at.is_(None),
            )
        )
    )


def test_list_and_sign_out_one(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, phone="9813000001")
    web, web_session = signed_in(db, client, member)
    app, app_session = signed_in(db, client, member, "app")
    push_on(web, 1)
    push_on(app, 2)

    listed = web.get("/api/v1/m/me/sessions").json()
    assert {(d["client"], d["current"]) for d in listed} == {
        ("web", True),
        ("app", False),
    }
    assert {d["device_label"] for d in listed} == {"web phone", "app phone"}

    # This device: "Sign out" is for that, not this.
    mine = web.post(f"/api/v1/m/me/sessions/{web_session.id}/sign-out")
    assert mine.status_code == 409
    gone = web.post(f"/api/v1/m/me/sessions/{app_session.id}/sign-out")
    assert gone.status_code == 204
    db.refresh(app_session)
    assert app_session.revoked_at is not None
    # The lost phone stops: signed out, and its notifications off.
    assert app.get("/api/v1/m/me").status_code == 401
    assert live_push(db, member) == {EXPO.format(1)}
    assert web.get("/api/v1/m/me").status_code == 200
    again = web.post(f"/api/v1/m/me/sessions/{app_session.id}/sign-out")
    assert again.status_code == 404
    actions = db.scalars(
        select(ActivityLog.action).where(ActivityLog.actor_id == member.id)
    ).all()
    assert "member.device_signed_out" in actions


def test_sign_out_the_others(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, phone="9813000002")
    here, _ = signed_in(db, client, member, "app")
    for n in range(2):
        other, _ = signed_in(db, client, member)
        push_on(other, 10 + n)
    push_on(here, 1)
    result = here.post("/api/v1/m/me/sessions/sign-out-others").json()
    assert result == {"signed_out": 2}
    assert [d["current"] for d in here.get("/api/v1/m/me/sessions").json()] == [True]
    assert live_push(db, member) == {EXPO.format(1)}


def test_another_members_device_is_not_found(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    sita = make_member(db, gym_a, phone="9813000003")
    family = make_member(db, gym_a, name="Gita", phone="9813000003")
    elsewhere = make_member(db, gym_b, phone="9813000003")
    mine, _ = signed_in(db, client, sita)
    for other in (family, elsewhere):
        _, theirs = signed_in(db, client, other)
        response = mine.post(f"/api/v1/m/me/sessions/{theirs.id}/sign-out")
        assert response.status_code == 404
        db.refresh(theirs)
        assert theirs.revoked_at is None
    assert len(mine.get("/api/v1/m/me/sessions").json()) == 1


def test_the_desk_signing_them_out_stops_notifications(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """Members → More → Sign out all devices, for a lost phone (§5.5)."""
    member = make_member(db, gym_a, phone="9813000004")
    phone, _ = signed_in(db, client, member, "app")
    push_on(phone, 1)
    sign_in(db, client, gym_a.owner)
    assert client.post(f"/api/v1/members/{member.id}/sign-out-all").status_code == 200
    assert live_push(db, member) == set()
    assert (
        db.scalars(
            select(MemberSession).where(
                MemberSession.member_id == member.id,
                MemberSession.revoked_at.is_(None),
            )
        ).all()
        == []
    )


def test_signing_out_turns_this_phones_notifications_off(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    member = make_member(db, gym_a, phone="9813000005")
    issued = member_auth.start_session(db, member, None, "app")
    db.commit()
    phone = TestClient(client.app)
    phone.headers["Authorization"] = f"Bearer {issued.access_token}"
    push_on(phone, 1)
    response = phone.post(
        "/api/v1/m/auth/logout", json={"refresh_token": issued.refresh_token}
    )
    assert response.status_code == 204
    assert live_push(db, member) == set()
