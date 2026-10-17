"""How GymBhai is doing, for /admin (PLAN.md §16.5, 10.1, 10.2)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal, utcnow
from app.models.billing import GymSubscription, PlatformPlan
from app.models.gym import GYM_SUSPENDED
from app.models.messaging import SmsMessage
from app.services import owner_messages, subscription
from tests.conftest import make_gym, make_member, sign_in

TODAY = today_in_nepal()


def aged(db: Session, fixture, days: int) -> None:
    """As if signed up `days` ago."""
    fixture.gym.created_at = utcnow() - dt.timedelta(days=days)
    db.commit()


def test_the_numbers(client: TestClient, db: Session, platform_admin) -> None:
    plan = PlatformPlan(name="Basic", monthly_price=1500_00)
    db.add(plan)
    db.commit()
    trial = make_gym(db, slug="stats-trial", phone="9841600001")
    paying = make_gym(db, slug="stats-paying", phone="9841600002")
    aged(db, paying, 30)
    subscription.extend(db, paying.gym.id, platform_plan_id=plan.id, months=1)
    lost = make_gym(db, slug="stats-lost", phone="9841600003")
    aged(db, lost, 90)
    subscription.extend(
        db, lost.gym.id, platform_plan_id=plan.id, ends_on=TODAY - dt.timedelta(days=20)
    )
    db.execute(
        update(GymSubscription)
        .where(GymSubscription.gym_id == lost.gym.id)
        .values(ends_on=TODAY - dt.timedelta(days=20))
    )
    gone = make_gym(db, slug="stats-gone", phone="9841600004")
    aged(db, gone, 40)  # trial over, never paid
    db.execute(
        update(GymSubscription)
        .where(GymSubscription.gym_id == gone.gym.id)
        .values(ends_on=TODAY - dt.timedelta(days=26))
    )
    suspended = make_gym(db, slug="stats-suspended", phone="9841600005")
    suspended.gym.status = GYM_SUSPENDED
    db.commit()

    sign_in(db, client, platform_admin)
    numbers = client.get("/api/v1/admin/summary").json()
    assert numbers["mrr"] == 1500_00  # the lost gym no longer counts
    assert numbers["by_state"] == {
        "trial": 1,
        "paying": 1,
        "grace": 0,
        "read_only": 2,
        "suspended": 1,
    }
    # Past their trial: paying, lost (paid once) and gone (never paid).
    assert (numbers["trials_ended"], numbers["trials_converted"]) == (3, 2)
    assert sum(m["gyms"] for m in numbers["lost_by_month"]) == 1
    states = {g["slug"]: g["state"] for g in client.get("/api/v1/admin/gyms").json()}
    assert states["stats-trial"] == "trial" and states["stats-paying"] == "paying"
    assert trial  # used above for the trial count


def test_gym_health(client: TestClient, db: Session, platform_admin) -> None:
    busy = make_gym(db, slug="health-busy", phone="9841600011")
    make_member(db, busy)
    quiet = make_gym(db, slug="health-quiet", phone="9841600012")
    aged(db, quiet, 30)
    sign_in(db, client, busy.owner)  # a staff sign-in this week
    aged(db, busy, 30)
    client.headers.pop("Authorization", None)
    client.cookies.clear()

    sign_in(db, client, platform_admin)
    gyms = {g["slug"]: g for g in client.get("/api/v1/admin/gyms").json()}
    assert gyms["health-busy"]["going_quiet"] is False
    assert gyms["health-busy"]["last_sign_in_at"] is not None
    assert gyms["health-busy"]["members_added_30d"] == 1
    assert gyms["health-busy"]["setup"]["first_member"] is True
    assert gyms["health-quiet"]["going_quiet"] is True
    assert client.get("/api/v1/admin/summary").json()["going_quiet"] == 1


def test_setup_nudges(db: Session) -> None:
    day3 = make_gym(db, slug="nudge-three", phone="9841600021")
    aged(db, day3, 3)
    day4 = make_gym(db, slug="nudge-four", phone="9841600022")
    aged(db, day4, 4)
    put_away = make_gym(db, slug="nudge-dismissed", phone="9841600023")
    aged(db, put_away, 3)
    put_away.gym.settings = {**put_away.gym.settings, "setup_dismissed": True}
    db.commit()

    assert owner_messages.setup_nudges(db) == 1
    db.commit()
    [text] = db.scalars(
        select(SmsMessage.body).where(SmsMessage.gym_id == day3.gym.id)
    ).all()
    assert "is 0 of 6 steps set up" in text
    assert "Next: set your plan prices" in text
