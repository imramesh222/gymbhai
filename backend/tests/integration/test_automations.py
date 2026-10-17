"""Automations (PLAN.md §16.3, 8.2): win-back, dues, not visiting, birthday.

Each is sent once per occasion, whatever the number of daily runs.
"""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal
from app.models.member_app import ALLOWED, CheckIn
from app.models.messaging import ReminderRule, SmsMessage
from app.services import reminders
from tests.conftest import GymFixture, make_member, sell, sign_in

TODAY = today_in_nepal()


def at(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(7), NEPAL)


def only(db: Session, gym: GymFixture, trigger: str) -> None:
    """Switch on just this trigger's automation: the expiry ones off."""
    db.execute(
        update(ReminderRule)
        .where(ReminderRule.gym_id == gym.gym.id)
        .values(enabled=ReminderRule.trigger == trigger)
    )
    db.commit()


def reminders_to(db: Session, member) -> list[str]:
    return list(
        db.scalars(
            select(SmsMessage.body).where(
                SmsMessage.member_id == member.id, SmsMessage.kind == "reminder"
            )
        )
    )


def run(db: Session, today: dt.date = TODAY) -> int:
    queued = reminders.run_daily(db, today)
    db.commit()
    return queued


def joined(db: Session, gym: GymFixture, phone: str, days_ago: int = 90):
    member = make_member(db, gym, phone=phone, name=f"Asha {phone[-2:]}")
    member.created_at = at(TODAY - dt.timedelta(days=days_ago))
    db.commit()
    return member


def test_win_back(db: Session, gym_a: GymFixture) -> None:
    only(db, gym_a, "lapsed")
    gone = joined(db, gym_a, "9800000301")
    sell(db, gym_a, gone, paid=1500_00, start_date=TODAY - dt.timedelta(days=60),
         end_date=TODAY - dt.timedelta(days=30))  # fmt: skip
    back = joined(db, gym_a, "9800000302")
    sell(db, gym_a, back, paid=1500_00, start_date=TODAY - dt.timedelta(days=60),
         end_date=TODAY - dt.timedelta(days=30))  # fmt: skip
    sell(db, gym_a, back, paid=1500_00, start_date=TODAY - dt.timedelta(days=29),
         end_date=TODAY + dt.timedelta(days=1))  # fmt: skip

    assert run(db) == 1
    assert "haven't seen you" in reminders_to(db, gone)[0]
    assert reminders_to(db, back) == []
    assert run(db) == 0  # once


def test_dues(db: Session, gym_a: GymFixture) -> None:
    only(db, gym_a, "dues")
    owing = joined(db, gym_a, "9800000311")
    membership, _ = sell(db, gym_a, owing, paid=500_00)
    paid = joined(db, gym_a, "9800000312")
    paid_membership, _ = sell(db, gym_a, paid, paid=1500_00)
    recent = joined(db, gym_a, "9800000313")
    sell(db, gym_a, recent, paid=0)  # sold today: not yet a week
    for m in (membership, paid_membership):
        m.created_at = at(TODAY - dt.timedelta(days=7))
    db.commit()

    assert run(db) == 1
    assert "Rs 1,000 is still to pay" in reminders_to(db, owing)[0]
    assert run(db) == 0
    assert run(db, TODAY + dt.timedelta(days=1)) == 0  # caught up, still once


def test_not_visiting(db: Session, gym_a: GymFixture) -> None:
    only(db, gym_a, "not_visiting")

    def regular(phone: str, last_visit: int):
        member = joined(db, gym_a, phone)
        sell(db, gym_a, member, paid=1500_00, start_date=TODAY - dt.timedelta(days=40),
             end_date=TODAY + dt.timedelta(days=40))  # fmt: skip
        visit(member, TODAY - dt.timedelta(days=last_visit))
        return member

    def visit(member, day: dt.date) -> None:
        db.add(
            CheckIn(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id,
                member_id=member.id,
                at=at(day),
                method="manual",
                result=ALLOWED,
            )
        )
        db.commit()

    away = regular("9800000321", last_visit=15)
    regular("9800000322", last_visit=3)  # still coming
    regular("9800000323", last_visit=30)  # gone before the rule was switched on

    assert run(db) == 1
    assert "It's been 15 days" in reminders_to(db, away)[0]
    assert run(db) == 0

    # They come back, then stop again: a new spell away, a new message.
    visit(away, TODAY)
    # A visit 14 days ago is still "within 14 days": day 15 is the first away.
    run(db, TODAY + dt.timedelta(days=14))
    assert len(reminders_to(db, away)) == 1
    run(db, TODAY + dt.timedelta(days=15))
    assert len(reminders_to(db, away)) == 2


def test_birthday(db: Session, gym_a: GymFixture) -> None:
    only(db, gym_a, "birthday")
    born = dt.date(1995, TODAY.month, min(TODAY.day, 28))
    today = born.replace(year=TODAY.year)
    member = joined(db, gym_a, "9800000331")
    member.date_of_birth = born
    sell(db, gym_a, member, start_date=today - dt.timedelta(days=5),
         end_date=today + dt.timedelta(days=25))  # fmt: skip
    lapsed = joined(db, gym_a, "9800000332")
    lapsed.date_of_birth = born  # not a current member: no birthday SMS
    db.commit()

    assert run(db, today) == 1
    assert reminders_to(db, member)[0].startswith("Happy birthday, Asha!")
    assert run(db, today + dt.timedelta(days=1)) == 0  # caught up, still once


def test_days_are_checked_for_each_trigger(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    rules = {
        (r["trigger"], r["days"]): r
        for r in client.get("/api/v1/reminder-rules").json()
    }

    def add(trigger: str, days: int):
        body = {"trigger": trigger, "days": days, "template": "Hi {name}!"}
        return client.post("/api/v1/reminder-rules", json=body)

    assert add("birthday", 3).status_code == 422
    assert add("not_visiting", 1).status_code == 422
    assert add("lapsed", 90).status_code == 201
    assert add("lapsed", 90).status_code == 409
    dues = rules[("dues", 7)]["id"]
    assert (
        client.patch(f"/api/v1/reminder-rules/{dues}", json={"days": 500}).status_code
        == 422
    )
    changed = client.patch(
        f"/api/v1/reminder-rules/{dues}", json={"days": 14, "enabled": True}
    )
    assert changed.json()["days"] == 14 and changed.json()["enabled"] is True
