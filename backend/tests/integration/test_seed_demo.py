"""The demo gym (scripts/seed_demo.py, PLAN.md §18.7): it still builds as the
services it uses change, and it adds up like a real gym's books."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.gym import Gym
from app.models.member_app import LET_IN, CheckIn
from app.models.membership import Membership
from app.services import memberships as ms
from scripts import seed_demo


def test_the_demo_gym_builds_and_adds_up(db: Session) -> None:
    counts, phone = seed_demo.build(db, members=14, say=lambda _: None)
    assert counts["members"] == 14
    assert counts["memberships"] >= 14 and counts["payments"] >= 14
    assert counts["visits"] > 100 and counts["expenses"] > 50
    assert counts["enquiries"] > 0 and counts["personal training"] > 0
    assert len(phone) == 10

    gym = db.scalar(select(Gym).where(Gym.slug == "demo"))
    assert gym is not None
    # On GymBhai for the year it has, so Reports' trends show all of it.
    assert (today_in_nepal() - gym.created_at.date()).days > 365
    memberships = db.scalars(
        select(Membership).where(Membership.gym_id == gym.id)
    ).all()
    payments = ms.payments_for(db, [m.id for m in memberships])
    for membership in memberships:
        paid = [p for p in payments if p.membership_id == membership.id]
        # Never more paid than owed.
        assert ms.dues_of(membership, paid) >= 0
    # Sold when they started (renewals a few days early), not when the demo
    # was made: the monthly report counts sales by that.
    for membership in memberships:
        sold = membership.created_at.astimezone(seed_demo.NEPAL).date()
        assert 0 <= (membership.start_date - sold).days <= 5
    # Let in only on a day their membership covered.
    spans = {m.id: (m.start_date, m.end_date) for m in memberships}
    for visit in db.scalars(
        select(CheckIn).where(CheckIn.gym_id == gym.id, CheckIn.result.in_(LET_IN))
    ):
        first, last = spans[visit.membership_id]
        assert first <= visit.at.astimezone(seed_demo.NEPAL).date() <= last

    # Made again from nothing, it's the same gym.
    again, _ = seed_demo.build(db, members=14, say=lambda _: None)
    assert again == counts


def test_it_refuses_to_run_in_production(monkeypatch) -> None:
    monkeypatch.setattr(seed_demo.settings, "environment", "production")
    assert seed_demo.main() == 1
