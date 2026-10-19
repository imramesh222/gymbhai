"""Signing in at the desk with a QR, no SMS code (PLAN.md §18.4)."""

import datetime as dt
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PRESETS
from app.core.time import utcnow
from app.jobs import cleanup
from app.models.activity import ActivityLog
from app.models.member_app import MemberSession, MemberSignInLink
from app.services import live
from tests.conftest import GymFixture, make_member, sell, sign_in

SLUG = "fitness-zone"


def make_link(client: TestClient, member_id) -> str:
    """Staff's QR, as the token in it."""
    response = client.post(f"/api/v1/members/{member_id}/sign-in-link")
    assert response.status_code == 200, response.text
    parts = urlsplit(response.json()["url"])
    assert parts.path == f"/{SLUG}"
    # In the fragment: never sent to a server, so never in a log.
    assert parts.fragment.startswith("desk=") and not parts.query
    return parts.fragment.removeprefix("desk=")


def scan(http: TestClient, token: str, slug: str = SLUG, **extra):
    """The member's phone, signed out, with the QR's link."""
    http.headers.pop("Authorization", None)
    return http.post(f"/api/v1/m/{slug}/desk-sign-in", json={"token": token, **extra})


def links(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(MemberSignInLink)) or 0


def test_the_phone_that_scans_it_is_signed_in(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sell(db, gym_a, member, paid=1500_00)
    sign_in(db, client, gym_a.owner)
    response = scan(client, make_link(client, member.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["me"]["name"] == "Sita Rai"
    assert body["me"]["qr"]["member_hex"] == member.id.hex
    # The web keeps its session in the cookie, as after a code.
    assert "gb_member_refresh" in client.cookies
    assert body["refresh_token"] is None

    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    assert client.get("/api/v1/m/me").json()["id"] == str(member.id)
    # The desk's profile of them now says when they signed in.
    sign_in(db, client, gym_a.owner)
    profile = client.get(f"/api/v1/members/{member.id}").json()
    assert profile["app_signed_in_at"] is not None

    made = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "member.sign_in_link_made")
    ).one()
    assert (made.actor_id, made.entity_id) == (gym_a.owner.id, member.id)
    used = db.scalars(
        select(ActivityLog).where(ActivityLog.action == "member.signed_in_at_desk")
    ).one()
    assert (used.actor_id, used.changes) == (
        member.id,
        {"shown_by": str(gym_a.owner.id)},
    )


def test_the_phone_app_keeps_its_own_token(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    body = scan(client, make_link(client, member.id), client="app").json()
    assert body["refresh_token"]
    session = db.scalars(
        select(MemberSession).where(MemberSession.member_id == member.id)
    ).one()
    assert session.client == "app"


def test_it_works_once_and_only_the_newest(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    first = make_link(client, member.id)
    newest = make_link(client, member.id)

    gone = scan(client, first)
    assert (gone.status_code, gone.json()["code"]) == (401, "sign_in_link_gone")
    assert scan(client, newest).status_code == 200
    assert scan(client, newest).status_code == 401


def test_it_runs_out(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    token = make_link(client, member.id)
    link = db.scalars(select(MemberSignInLink)).one()
    assert link.expires_at - utcnow() <= dt.timedelta(minutes=5)
    link.expires_at = utcnow() - dt.timedelta(seconds=1)
    db.commit()
    assert scan(client, token).status_code == 401


def test_another_gyms_address_signs_nobody_in(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    token = make_link(client, member.id)
    assert scan(client, token, slug=gym_b.gym.slug).status_code == 401
    # And the try there didn't use it up.
    assert scan(client, token).status_code == 200


def test_only_for_members_with_the_app(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    token = make_link(client, member.id)
    # Access turned off after the QR was made: it stops working.
    client.patch(f"/api/v1/members/{member.id}/access", json={"app_access": False})
    refused = client.post(f"/api/v1/members/{member.id}/sign-in-link")
    assert (refused.status_code, refused.json()["code"]) == (409, "no_app_access")
    assert scan(client, token).status_code == 401


def test_the_front_desk_can_show_it(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    """The Front desk starting point includes app access (§18.4)."""
    member = make_member(db, gym_a)
    desk = make_staff(gym_a.gym, permissions=[p.value for p in PRESETS["front_desk"]])
    sign_in(db, client, desk)
    assert client.post(f"/api/v1/members/{member.id}/sign-in-link").status_code == 200

    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    refused = client.post(f"/api/v1/members/{member.id}/sign-in-link")
    assert refused.json()["permission"] == "members.app_access"


def test_erasing_a_member_removes_their_qrs(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    make_link(client, member.id)
    assert client.post(f"/api/v1/members/{member.id}/erase").status_code == 200
    assert links(db) == 0


def test_old_ones_are_cleaned_up(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    make_link(client, member.id)
    cleanup(db, {})
    assert links(db) == 1  # a day past expiry first
    db.scalars(select(MemberSignInLink)).one().expires_at = utcnow() - dt.timedelta(
        days=2
    )
    db.commit()
    cleanup(db, {})
    assert links(db) == 0


def test_the_desk_sees_the_phone_sign_in(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
):
    calls: list[dict] = []
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    token = make_link(client, member.id)
    monkeypatch.setattr(live, "publish", lambda db, **kwargs: calls.append(kwargs))
    scan(client, token)
    assert calls == [
        {
            "gym_id": gym_a.gym.id,
            "kind": live.MEMBER,
            "member_id": member.id,
            "branch_id": member.home_branch_id,
        }
    ]
