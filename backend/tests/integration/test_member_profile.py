"""The member app, more of it theirs (PLAN.md §16.3, 8.5): their own details,
a new email confirmed by a code, their photo, and how busy the gym is."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.models.activity import ACTOR_MEMBER, ActivityLog
from app.models.member_app import ALLOWED, CheckIn
from app.services import checkins, member_auth
from tests.conftest import GymFixture, make_member, sell

CODE = "123456"


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: int(CODE))


@pytest.fixture(autouse=True)
def files_in_a_scratch_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))


def signed_in(client: TestClient, gym: GymFixture, member) -> None:
    slug = gym.gym.slug
    client.post(f"/api/v1/m/{slug}/otp/request", json={"phone": member.phone})
    body = client.post(
        f"/api/v1/m/{slug}/otp/verify", json={"phone": member.phone, "code": CODE}
    ).json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"


def own_actions(db: Session, member) -> list[ActivityLog]:
    return list(
        db.scalars(
            select(ActivityLog).where(
                ActivityLog.actor_type == ACTOR_MEMBER,
                ActivityLog.actor_id == member.id,
            )
        )
    )


def test_their_emergency_contact(client: TestClient, db: Session, gym_a) -> None:
    member = make_member(db, gym_a)
    signed_in(client, gym_a, member)
    me = client.patch(
        "/api/v1/m/me", json={"emergency_contact": "Ram (brother) 9811111111"}
    )
    assert me.json()["emergency_contact"] == "Ram (brother) 9811111111"
    [logged] = [a for a in own_actions(db, member) if a.action == "member.updated_own"]
    assert logged.changes["emergency_contact"]["after"] == "Ram (brother) 9811111111"
    # The phone isn't theirs to change: the gym knows them by it.
    assert client.patch("/api/v1/m/me", json={"phone": "9800000000"}).status_code == 422


def test_a_new_email_needs_its_code(client: TestClient, db: Session, gym_a) -> None:
    member = make_member(db, gym_a)
    signed_in(client, gym_a, member)
    new = "sita@example.com"
    assert client.post("/api/v1/m/me/email", json={"email": new}).status_code == 204
    # Nothing changes until the code is typed.
    assert client.get("/api/v1/m/me").json()["email"] is None
    wrong = client.post(
        "/api/v1/m/me/email/confirm", json={"email": new, "code": "000000"}
    )
    assert wrong.status_code == 401
    right = client.post("/api/v1/m/me/email/confirm", json={"email": new, "code": CODE})
    assert right.json()["email"] == new
    assert any(a.action == "member.email_changed" for a in own_actions(db, member))
    # Used up.
    again = client.post("/api/v1/m/me/email/confirm", json={"email": new, "code": CODE})
    assert again.status_code == 401


def test_another_members_code_or_the_master_code_wont_do(
    client: TestClient, db: Session, gym_a, monkeypatch
) -> None:
    mine = make_member(db, gym_a, phone="9800000601")
    theirs = make_member(db, gym_a, phone="9800000602", name="Hari")
    target = "shared@example.com"
    signed_in(client, gym_a, theirs)
    client.post("/api/v1/m/me/email", json={"email": target})
    signed_in(client, gym_a, mine)
    # Hari's code for that address is not Sita's.
    stolen = client.post(
        "/api/v1/m/me/email/confirm", json={"email": target, "code": CODE}
    )
    assert stolen.status_code == 401
    monkeypatch.setattr(settings, "master_otp", "135790")
    client.post("/api/v1/m/me/email", json={"email": "other@example.com"})
    master = client.post(
        "/api/v1/m/me/email/confirm",
        json={"email": "other@example.com", "code": "135790"},
    )
    assert master.status_code == 401


def test_their_photo(client: TestClient, db: Session, gym_a) -> None:
    member = make_member(db, gym_a)
    signed_in(client, gym_a, member)
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    me = client.post("/api/v1/m/me/photo", files={"file": ("me.png", png, "image/png")})
    assert me.status_code == 200
    assert me.json()["photo_url"]
    assert any(a.action == "member.photo_changed" for a in own_actions(db, member))


def visits(db: Session, gym: GymFixture, member, at: dt.datetime, n: int) -> None:
    for i in range(n):
        db.add(
            CheckIn(
                gym_id=gym.gym.id,
                branch_id=gym.branch.id,
                member_id=member.id,
                at=at - dt.timedelta(minutes=i),
                method="manual",
                result=ALLOWED,
            )
        )
    db.commit()


def test_how_busy(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    member = make_member(db, gym_a)
    sell(db, gym_a, member)
    now = utcnow()
    busy = lambda: checkins.busyness(db, gym_a.gym.id, gym_a.branch.id, now)  # noqa: E731
    assert busy() is None  # nothing to compare with yet
    for week in range(1, 5):  # 10 a time, the same hours, the last four weeks
        visits(db, gym_a, member, now - dt.timedelta(weeks=week, minutes=30), 10)
    assert busy() == "quiet"
    visits(db, gym_a, member, now - dt.timedelta(minutes=30), 10)
    assert busy() == "normal"
    visits(db, gym_a, member, now - dt.timedelta(minutes=50), 5)
    assert busy() == "busy"

    signed_in(client, gym_a, member)
    assert client.get("/api/v1/m/me").json()["busy"] in ("normal", "busy")
    gym_a.gym.settings = {**gym_a.gym.settings, "show_busyness": False}
    db.commit()
    assert client.get("/api/v1/m/me").json()["busy"] is None
