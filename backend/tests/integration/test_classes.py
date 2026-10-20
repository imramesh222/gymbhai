"""Group classes (PLAN.md §19.4): the timetable makes the classes, places are
counted with a waitlist, the plan says who may book, and who came."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import NEPAL, today_in_nepal, utcnow
from app.models.activity import ActivityLog
from app.models.classes import ClassBooking, ClassSlot, ClassType, GymClass
from app.models.gym import Gym
from app.models.job import Job
from app.models.member_app import CheckIn
from app.services import checkins, member_auth
from app.services import classes as service
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()
TOMORROW = TODAY + dt.timedelta(days=1)


def zumba(db: Session, gym: GymFixture, *, places: int = 2) -> ClassType:
    kind = ClassType(gym_id=gym.gym.id, name="Zumba", minutes=60, places=places)
    db.add(kind)
    db.commit()
    return kind


def slot_on(
    db: Session, gym: GymFixture, kind: ClassType, day: dt.date, starts="07:00"
) -> ClassSlot:
    slot = ClassSlot(
        gym_id=gym.gym.id,
        branch_id=gym.branch.id,
        type_id=kind.id,
        weekday=day.weekday(),
        starts=starts,
        minutes=kind.minutes,
        places=kind.places,
        instructor_id=gym.owner.id,
    )
    db.add(slot)
    db.flush()
    service.generate(db, slot_id=slot.id)
    db.commit()
    return slot


def class_on(db: Session, slot: ClassSlot, day: dt.date) -> GymClass:
    start = service.starts_at(day, slot.starts)
    return db.scalars(
        select(GymClass).where(GymClass.slot_id == slot.id, GymClass.starts_at == start)
    ).one()


def member_with_plan(db: Session, gym: GymFixture, phone: str, name="Sita", **plan_kw):
    member = make_member(db, gym, name=name, phone=phone)
    plan = priced_plan(db, gym.gym)
    for key, value in plan_kw.items():
        setattr(plan, key, value)
    db.commit()
    sell(db, gym, member, plan=plan, paid=1_500_00)
    return member


def app_for(client: TestClient, db: Session, member) -> TestClient:
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    return app


@pytest.fixture
def tomorrow_class(db: Session, gym_a: GymFixture) -> GymClass:
    slot = slot_on(db, gym_a, zumba(db, gym_a), TOMORROW)
    return class_on(db, slot, TOMORROW)


# --- the timetable ------------------------------------------------------------------


def test_the_timetable_makes_four_weeks_of_classes_once(
    db: Session, gym_a: GymFixture
) -> None:
    slot = slot_on(db, gym_a, zumba(db, gym_a), TOMORROW)
    made = db.scalars(select(GymClass).where(GymClass.slot_id == slot.id)).all()
    assert len(made) == 4
    assert {c.starts_at.astimezone(NEPAL).weekday() for c in made} == {slot.weekday}
    assert service.generate(db) == 0  # the worker again: nothing new


def test_changing_the_timetable_moves_only_unbooked_classes(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    slot = slot_on(db, gym_a, zumba(db, gym_a), TOMORROW)
    booked = class_on(db, slot, TOMORROW)
    sita = member_with_plan(db, gym_a, "9812000001")
    service.book(db, db.get(Gym, gym_a.gym.id), sita, booked)
    db.commit()

    sign_in(db, client, gym_a.owner)
    response = client.patch(f"/api/v1/class-slots/{slot.id}", json={"starts": "18:00"})
    assert response.status_code == 200, response.text
    db.refresh(booked)
    assert booked.starts_at.astimezone(NEPAL).strftime("%H:%M") == "07:00"
    later = db.scalars(
        select(GymClass).where(GymClass.slot_id == slot.id, GymClass.id != booked.id)
    ).all()
    assert {c.starts_at.astimezone(NEPAL).strftime("%H:%M") for c in later} == {"18:00"}


# --- booking -----------------------------------------------------------------------


def test_places_then_the_waitlist_then_a_place_given_back(
    client: TestClient, db: Session, gym_a: GymFixture, tomorrow_class: GymClass
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    people = [
        member_with_plan(db, gym_a, f"98120000{i}", name=f"M{i}") for i in range(3)
    ]
    bookings = [service.book(db, gym, m, tomorrow_class) for m in people]
    db.commit()
    assert [b.status for b in bookings] == ["booked", "booked", "waitlist"]

    service.cancel_booking(db, gym, bookings[0], tomorrow_class)
    db.commit()
    db.refresh(bookings[2])
    assert bookings[2].status == "booked"
    assert db.scalars(
        select(ActivityLog).where(ActivityLog.action == "class_booking.promoted")
    ).one()
    # Reminders an hour before, for each place held.
    assert (
        len(db.scalars(select(Job).where(Job.kind == service.JOB_REMINDER)).all()) == 3
    )


def test_who_may_book(db: Session, gym_a: GymFixture, tomorrow_class: GymClass) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    nobody = make_member(db, gym_a, name="No plan", phone="9812000009")
    assert service.why_not(db, gym, nobody, tomorrow_class)[0] == "no_membership"
    gym_only = member_with_plan(db, gym_a, "9812000010", classes="none")
    assert service.why_not(db, gym, gym_only, tomorrow_class)[0] == "plan_no_class"

    yoga = ClassType(gym_id=gym_a.gym.id, name="Yoga")
    db.add(yoga)
    db.commit()
    yoga_only = member_with_plan(
        db, gym_a, "9812000011", classes="chosen", class_type_ids=[str(yoga.id)]
    )
    assert service.why_not(db, gym, yoga_only, tomorrow_class)[0] == "plan_no_class"
    zumba_too = member_with_plan(
        db,
        gym_a,
        "9812000012",
        classes="chosen",
        class_type_ids=[str(yoga.id), str(tomorrow_class.type_id)],
    )
    assert service.why_not(db, gym, zumba_too, tomorrow_class) is None


def test_the_booking_window(client: TestClient, db: Session, gym_a: GymFixture) -> None:
    kind = zumba(db, gym_a)
    far = TODAY + dt.timedelta(days=20)
    slot = slot_on(db, gym_a, kind, far)
    later = class_on(db, slot, far)
    sita = member_with_plan(db, gym_a, "9812000001")
    app = app_for(client, db, sita)
    early = app.post(f"/api/v1/m/classes/{later.id}/book")
    assert early.json()["code"] == "booking_not_open"

    # Closing in 30 minutes: too late from the app, fine at the desk.
    soon = GymClass(
        gym_id=gym_a.gym.id,
        branch_id=gym_a.branch.id,
        type_id=kind.id,
        starts_at=utcnow() + dt.timedelta(minutes=10),
        ends_at=utcnow() + dt.timedelta(minutes=70),
        places=5,
    )
    db.add(soon)
    db.commit()
    assert app.post(f"/api/v1/m/classes/{soon.id}/book").json()["code"] == (
        "booking_closed"
    )
    sign_in(db, client, gym_a.owner)
    desk = client.post(
        f"/api/v1/classes/{soon.id}/bookings", json={"member_id": str(sita.id)}
    )
    assert desk.status_code == 201, desk.text
    assert [b["status"] for b in desk.json()["bookings"]] == ["booked"]


def test_once_each_and_again_after_cancelling(
    client: TestClient, db: Session, gym_a: GymFixture, tomorrow_class: GymClass
) -> None:
    sita = member_with_plan(db, gym_a, "9812000001")
    app = app_for(client, db, sita)
    first = app.post(
        f"/api/v1/m/classes/{tomorrow_class.id}/book",
        headers={"Idempotency-Key": "0b7c9f2e-4d1a-4e8b-9a36-1f2d3c4b5a60"},
    )
    again = app.post(
        f"/api/v1/m/classes/{tomorrow_class.id}/book",
        headers={"Idempotency-Key": "0b7c9f2e-4d1a-4e8b-9a36-1f2d3c4b5a60"},
    )
    assert first.status_code == 200, first.text
    assert again.json() == first.json()
    [listed] = [c for c in first.json()["classes"] if c["id"] == str(tomorrow_class.id)]
    assert listed["mine"] == "booked" and listed["places_left"] == 1
    assert app.post(f"/api/v1/m/classes/{tomorrow_class.id}/book").json()["code"] == (
        "already_booked"
    )
    cancelled = app.post(f"/api/v1/m/class-bookings/{listed['booking_id']}/cancel")
    assert cancelled.status_code == 200
    rebooked = app.post(f"/api/v1/m/classes/{tomorrow_class.id}/book")
    assert rebooked.status_code == 200, rebooked.text


def test_a_late_cancel_and_no_shows_pause_booking(
    db: Session, gym_a: GymFixture
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    gym.settings = {**gym.settings, "no_show_limit": 1}
    db.commit()
    kind = zumba(db, gym_a, places=5)
    sita = member_with_plan(db, gym_a, "9812000001")
    # A class that ended yesterday, booked, and she never came.
    past = GymClass(
        gym_id=gym.id,
        branch_id=gym_a.branch.id,
        type_id=kind.id,
        starts_at=utcnow() - dt.timedelta(days=1),
        ends_at=utcnow() - dt.timedelta(days=1) + dt.timedelta(hours=1),
        places=5,
    )
    db.add(past)
    db.flush()
    db.add(
        ClassBooking(
            gym_id=gym.id,
            class_id=past.id,
            member_id=sita.id,
            status="booked",
            booked_at=utcnow() - dt.timedelta(days=2),
        )
    )
    db.commit()
    soon = class_on(db, slot_on(db, gym_a, kind, TOMORROW), TOMORROW)
    assert service.no_shows(db, sita.id) == 1
    assert service.why_not(db, gym, sita, soon)[0] == "no_shows"

    # Had she come through the door, it isn't a no-show.
    db.add(
        CheckIn(
            gym_id=gym.id,
            branch_id=gym_a.branch.id,
            member_id=sita.id,
            at=past.starts_at - dt.timedelta(minutes=20),
            method="manual",
            result="allowed",
        )
    )
    db.commit()
    assert service.no_shows(db, sita.id) == 0


# --- the desk and the instructor -------------------------------------------------


def test_the_roster_and_who_came(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    kind = zumba(db, gym_a, places=5)
    now_class = GymClass(
        gym_id=gym.id,
        branch_id=gym_a.branch.id,
        type_id=kind.id,
        starts_at=utcnow() - dt.timedelta(minutes=10),
        ends_at=utcnow() + dt.timedelta(minutes=50),
        places=5,
        instructor_id=gym_a.owner.id,
    )
    db.add(now_class)
    db.commit()
    door = member_with_plan(db, gym_a, "9812000001", name="Came by the door")
    ticked = member_with_plan(db, gym_a, "9812000002", name="Ticked")
    for m in (door, ticked):
        db.add(
            ClassBooking(
                gym_id=gym.id,
                class_id=now_class.id,
                member_id=m.id,
                status="booked",
                booked_at=utcnow() - dt.timedelta(hours=3),
            )
        )
    db.commit()
    checkins.check_in(
        db, gym=gym, member=door, branch_id=gym_a.branch.id, method="manual"
    )
    db.commit()

    other_trainer = make_staff(gym, permissions=["classes.teach", "members.view"])
    sign_in(db, client, other_trainer)
    roster = client.get(f"/api/v1/classes/{now_class.id}").json()
    by_name = {b["member_name"]: b for b in roster["bookings"]}
    assert by_name["Came by the door"]["came"] is True
    assert by_name["Ticked"]["came"] is False
    refused = client.post(
        f"/api/v1/class-bookings/{by_name['Ticked']['id']}/attended",
        json={"came": True},
    )
    assert refused.json()["code"] == "not_your_class"

    sign_in(db, client, gym_a.owner)  # its instructor
    marked = client.post(
        f"/api/v1/class-bookings/{by_name['Ticked']['id']}/attended",
        json={"came": True},
    )
    assert {b["member_name"]: b["came"] for b in marked.json()["bookings"]} == {
        "Came by the door": True,
        "Ticked": True,
    }


def test_cancelling_a_class_tells_everyone(
    client: TestClient, db: Session, gym_a: GymFixture, tomorrow_class: GymClass
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    sita = member_with_plan(db, gym_a, "9812000001")
    service.book(db, gym, sita, tomorrow_class)
    db.commit()
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/classes/{tomorrow_class.id}/cancel",
        json={"reason": "The instructor is ill.", "sms": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cancelled_at"] is not None
    from app.models.messaging import SmsMessage

    [told] = db.scalars(select(SmsMessage).where(SmsMessage.member_id == sita.id))
    assert "cancelled" in told.body and "The instructor is ill." in told.body


def test_permissions(
    client: TestClient, db: Session, gym_a: GymFixture, tomorrow_class, make_staff
) -> None:
    sita = member_with_plan(db, gym_a, "9812000001")
    teacher = make_staff(gym_a.gym, permissions=["classes.teach", "members.view"])
    sign_in(db, client, teacher)
    assert client.get("/api/v1/classes").status_code == 200
    booked = client.post(
        f"/api/v1/classes/{tomorrow_class.id}/bookings",
        json={"member_id": str(sita.id)},
    )
    assert booked.status_code == 403
    assert (
        client.post(
            f"/api/v1/classes/{tomorrow_class.id}/cancel", json={"reason": "not mine"}
        ).status_code
        == 403
    )
    nobody = make_staff(gym_a.gym, permissions=["members.view"])
    sign_in(db, client, nobody)
    assert client.get("/api/v1/classes").status_code == 403


def test_a_plan_includes_only_this_gyms_classes(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    theirs = zumba(db, gym_b)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/plans",
        json={
            "name": "Zumba month",
            "duration_months": 1,
            "classes": "chosen",
            "class_type_ids": [str(theirs.id)],
        },
    )
    assert response.json()["code"] == "bad_class_type"


# --- the member app -------------------------------------------------------------


def test_the_week_in_the_app(
    client: TestClient, db: Session, gym_a: GymFixture, tomorrow_class: GymClass
) -> None:
    gym_only = member_with_plan(db, gym_a, "9812000010", classes="none")
    week = app_for(client, db, gym_only).get("/api/v1/m/classes").json()
    [listed] = week["classes"]
    assert listed["type_name"] == "Zumba"
    assert listed["blocked"] == "plan_no_class"
    assert (week["booking_days"], week["cancel_hours"]) == (7, 2)


def test_the_reminder_an_hour_before(
    db: Session, gym_a: GymFixture, tomorrow_class: GymClass
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    sita = member_with_plan(db, gym_a, "9812000001")
    booking = service.book(db, gym, sita, tomorrow_class)
    db.commit()
    [job] = db.scalars(select(Job).where(Job.kind == service.JOB_REMINDER))
    assert job.run_at == tomorrow_class.starts_at - service.REMINDER_BEFORE
    # Run now: she has no phone with push, so nothing is sent, and nothing fails.
    service.handle_reminder(db, {"booking_id": str(booking.id)})


def test_the_month_on_reports(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    gym = db.get(Gym, gym_a.gym.id)
    kind = zumba(db, gym_a, places=10)
    earlier = GymClass(
        gym_id=gym.id,
        branch_id=gym_a.branch.id,
        type_id=kind.id,
        starts_at=utcnow() - dt.timedelta(hours=3),
        ends_at=utcnow() - dt.timedelta(hours=2),
        places=10,
        instructor_id=gym_a.owner.id,
    )
    db.add(earlier)
    db.flush()
    came = member_with_plan(db, gym_a, "9812000001", name="Came")
    missed = member_with_plan(db, gym_a, "9812000002", name="Missed")
    for m, attended in ((came, True), (missed, None)):
        db.add(
            ClassBooking(
                gym_id=gym.id,
                class_id=earlier.id,
                member_id=m.id,
                status="booked",
                booked_at=utcnow() - dt.timedelta(days=1),
                attended=attended,
            )
        )
    db.commit()
    sign_in(db, client, gym_a.owner)
    figures = client.get("/api/v1/reports/monthly").json()["classes"]
    assert {
        k: figures[k] for k in ("held", "places", "booked", "came", "no_shows")
    } == {
        "held": 1,
        "places": 10,
        "booked": 2,
        "came": 1,
        "no_shows": 1,
    }
    assert figures["by_type"][0]["name"] == "Zumba"
    assert figures["by_instructor"][0]["held"] == 1


def test_the_booking_rules_are_for_whoever_manages_classes(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
) -> None:
    desk = make_staff(gym_a.gym, permissions=["classes.book"])
    sign_in(db, client, desk)
    refused = client.patch("/api/v1/gym/class-rules", json={"no_show_limit": 3})
    assert refused.status_code == 403
    sign_in(db, client, gym_a.owner)
    changed = client.patch(
        "/api/v1/gym/class-rules", json={"no_show_limit": 3, "class_booking_days": 14}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["settings"]["no_show_limit"] == 3
    assert changed.json()["settings"]["class_booking_days"] == 14


def test_the_app_shows_a_class_they_were_booked_into_at_another_branch(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    from app.models.gym import Branch

    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    kind = zumba(db, gym_a)
    there = GymClass(
        gym_id=gym_a.gym.id,
        branch_id=other.id,
        type_id=kind.id,
        starts_at=utcnow() + dt.timedelta(days=1),
        ends_at=utcnow() + dt.timedelta(days=1, hours=1),
        places=5,
    )
    db.add(there)
    db.commit()
    sita = member_with_plan(db, gym_a, "9812000001")
    app = app_for(client, db, sita)
    assert app.get("/api/v1/m/classes").json()["classes"] == []
    service.book(db, db.get(Gym, gym_a.gym.id), sita, there, staff=gym_a.owner)
    db.commit()
    [listed] = app.get("/api/v1/m/classes").json()["classes"]
    assert listed["mine"] == "booked"
