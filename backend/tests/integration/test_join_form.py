"""The public join form behind the gym QR (PLAN.md §16.4, 9.5)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.member import Member
from app.services import leads
from tests.conftest import GymFixture, make_member, sign_in


def turn_on(client: TestClient, db: Session, gym: GymFixture) -> None:
    sign_in(db, client, gym.owner)
    response = client.patch("/api/v1/gym", json={"settings": {"join_form": True}})
    assert response.status_code == 200, response.text
    client.headers.pop("Authorization", None)
    client.cookies.clear()


def ask(client: TestClient, gym: GymFixture, **fields):
    body = {"name": "Maya Tamang", "phone": "9800000951", **fields}
    return client.post(f"/api/v1/m/{gym.gym.slug}/join", json=body)


def test_off_unless_the_gym_turns_it_on(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    assert client.get(f"/api/v1/m/{gym_a.gym.slug}/join").status_code == 404
    assert ask(client, gym_a).status_code == 404
    assert client.get(f"/api/v1/m/{gym_a.gym.slug}/gym").json()["join_form"] is False


def test_an_enquiry_never_a_member(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a)
    options = client.get(f"/api/v1/m/{gym_a.gym.slug}/join").json()
    plan_id = options["plans"][0]["id"]
    response = ask(
        client, gym_a, plan_id=plan_id, source="instagram", message="Mornings?"
    )
    assert response.status_code == 202
    lead = db.scalars(select(Lead)).one()
    assert (lead.name, lead.source, lead.notes) == (
        "Maya Tamang",
        "instagram",
        "Mornings?",
    )
    assert str(lead.plan_id) == plan_id and lead.follow_up_on is not None
    assert lead.from_ip is not None
    assert db.scalars(select(Member).where(Member.phone == "9800000951")).all() == []

    # Again from the same number: the same enquiry, not a second one.
    ask(client, gym_a, message="Evenings too")
    lead = db.scalars(select(Lead)).one()
    assert lead.notes == "Mornings?\nEvenings too"


def test_the_same_answer_for_members(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    make_member(db, gym_a, phone="9800000952")
    turn_on(client, db, gym_a)
    member = ask(client, gym_a, phone="9800000952")
    stranger = ask(client, gym_a, phone="9800000953")
    assert member.status_code == stranger.status_code == 202
    assert member.json() == stranger.json()


def test_rate_limited_per_ip(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    turn_on(client, db, gym_a)
    for n in range(leads.JOIN_PER_IP_HOUR):
        assert ask(client, gym_a, phone=f"98000009{60 + n}").status_code == 202
    assert ask(client, gym_a, phone="9800000999").status_code == 429


def test_the_ip_is_kept_a_day(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    from app.jobs import cleanup

    turn_on(client, db, gym_a)
    ask(client, gym_a)
    db.execute(update(Lead).values(created_at=Lead.created_at - dt.timedelta(days=2)))
    db.commit()
    cleanup(db, {})
    db.commit()
    assert db.scalars(select(Lead.from_ip)).one() is None
