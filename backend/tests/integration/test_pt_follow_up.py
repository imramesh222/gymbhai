"""Personal training's reminders, Follow up and Reports (PLAN.md §18.3)."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.calendar import format_date
from app.core.time import today_in_nepal, utcnow
from app.models.gym import Branch
from app.models.training import PtPackage, PtPlan, PtSession
from app.services import memberships as ms
from app.services import training
from tests.conftest import GymFixture, context_for, make_member, sell, sign_in
from tests.integration.test_automations import at, joined, only, reminders_to, run
from tests.integration.test_personal_training import pt_plan

TODAY = today_in_nepal()


def sell_pt(
    db: Session,
    gym: GymFixture,
    member,
    plan: PtPlan,
    *,
    paid: int = 0,
    sold_days_ago: int = 0,
    trainer=None,
    **sale,
) -> PtPackage:
    """Sold through the service, as the desk does, `sold_days_ago` days ago."""
    package, _ = training.sell(
        db,
        context_for(db, gym.owner),
        member,
        training.SaleIn(
            plan_id=plan.id,
            trainer_id=(trainer or gym.owner).id,
            payment=ms.PaymentIn(amount=paid, method="cash") if paid else None,
            **sale,
        ),
        gym.gym.config,
    )
    package.created_at = at(TODAY - dt.timedelta(days=sold_days_ago))
    db.commit()
    return package


def trained(db: Session, package: PtPackage, *days: dt.date, voided=False) -> None:
    for day in days:
        db.add(
            PtSession(
                gym_id=package.gym_id,
                package_id=package.id,
                trained_on=day,
                trainer_id=package.trainer_id,
                voided_at=utcnow() if voided else None,
            )
        )
    db.commit()


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


# --- reminders ----------------------------------------------------------------


def test_ending_counts_from_their_last_package(db: Session, gym_a: GymFixture):
    only(db, gym_a, "pt_ending")  # 3 days before, and the day after
    monthly = pt_plan(db, gym_a.gym, kind="monthly", months=1)
    pack = pt_plan(db, gym_a.gym, sessions=4, months=2)

    ending = joined(db, gym_a, "9800000401")
    sell_pt(db, gym_a, ending, monthly, start_date=days(-27), end_date=days(3))
    renewed = joined(db, gym_a, "9800000402")
    # The next one entered first: the order they were entered in can't matter.
    sell_pt(db, gym_a, renewed, monthly, start_date=days(4))
    sell_pt(db, gym_a, renewed, monthly, start_date=days(-27), end_date=days(3))
    # A pack used up yesterday, weeks before its end date.
    used_up = joined(db, gym_a, "9800000403")
    package = sell_pt(db, gym_a, used_up, pack, start_date=days(-20))
    trained(db, package, days(-10), days(-7), days(-4), days(-1))
    cancelled = joined(db, gym_a, "9800000404")
    gone = sell_pt(
        db, gym_a, cancelled, monthly, start_date=days(-27), end_date=days(3)
    )
    gone.cancelled_at = utcnow()
    db.commit()

    assert run(db) == 2
    shown = gym_a.gym.config.date_display
    [soon] = reminders_to(db, ending)
    assert f"ends on {format_date(days(3), shown)}" in soon
    assert "training with Owner," in soon  # the trainer's first name
    [over] = reminders_to(db, used_up)
    assert f"ended on {format_date(days(-1), shown)}" in over
    assert reminders_to(db, renewed) == reminders_to(db, cancelled) == []
    assert run(db) == 0  # once
    assert run(db, days(1)) == 0


def test_money_owed_on_personal_training(db: Session, gym_a: GymFixture):
    only(db, gym_a, "pt_dues")  # a week after the sale
    plan = pt_plan(db, gym_a.gym, price=12_000_00)
    owing = joined(db, gym_a, "9800000411")
    sell_pt(db, gym_a, owing, plan, paid=5_000_00, sold_days_ago=7)
    settled = joined(db, gym_a, "9800000412")
    sell_pt(db, gym_a, settled, plan, paid=12_000_00, sold_days_ago=7)
    recent = joined(db, gym_a, "9800000413")
    sell_pt(db, gym_a, recent, plan, sold_days_ago=2)
    cancelled = joined(db, gym_a, "9800000414")
    gone = sell_pt(db, gym_a, cancelled, plan, sold_days_ago=7)
    gone.cancelled_at = utcnow()
    db.commit()
    # A membership owed is the dues automation's, not this one's.
    sell(db, gym_a, settled, paid=0)

    assert run(db) == 1
    [text] = reminders_to(db, owing)
    assert "Rs 7,000 is still to pay for your personal training" in text
    assert run(db) == 0
    assert run(db, days(1)) == 0  # caught up, still once


def test_rules_for_personal_training(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sign_in(db, client, gym_a.owner)
    body = {"trigger": "pt_ending", "days": -7, "template": "Hi {name}, soon"}
    assert client.post("/api/v1/reminder-rules", json=body).status_code == 201
    too_far = {**body, "days": 61}
    assert client.post("/api/v1/reminder-rules", json=too_far).status_code == 422
    no_days = {"trigger": "pt_dues", "days": 0, "template": "Hi {name}, pay"}
    assert client.post("/api/v1/reminder-rules", json=no_days).status_code == 422


# --- Follow up ----------------------------------------------------------------


def test_follow_up_lists_what_is_owed_on_personal_training(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    plan = pt_plan(db, gym_a.gym, price=12_000_00)
    owing = make_member(db, gym_a, name="Ram Thapa", phone="9800000421")
    sell_pt(db, gym_a, owing, plan, paid=2_000_00)
    settled = make_member(db, gym_a, name="Gita Rai", phone="9800000422")
    sell_pt(db, gym_a, settled, plan, paid=12_000_00)
    archived = make_member(db, gym_a, name="Old Member", phone="9800000423")
    sell_pt(db, gym_a, archived, plan)
    archived.is_archived = True
    cancelled = make_member(db, gym_a, name="Changed Mind", phone="9800000424")
    gone = sell_pt(db, gym_a, cancelled, plan)
    gone.cancelled_at = utcnow()
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    elsewhere = make_member(db, gym_a, name="Hari Karki", phone="9800000425")
    sell_pt(db, gym_a, elsewhere, plan, paid=11_000_00, branch_id=other.id)

    sign_in(db, client, gym_a.owner)
    lists = client.get("/api/v1/lists/follow-up").json()
    assert [
        (row["name"], row["dues"], row["trainer_name"], row["plan_name"])
        for row in lists["pt_owing"]
    ] == [
        ("Ram Thapa", 10_000_00, gym_a.owner.name, plan.name),
        ("Hari Karki", 1_000_00, gym_a.owner.name, plan.name),
    ]
    assert lists["pt_owing_total"] == 2
    assert lists["owing"] == []  # memberships' dues stay apart

    # WhatsApp from the row: what they owe on personal training.
    text = client.get(f"/api/v1/members/{owing.id}/message?purpose=pt_dues")
    assert (
        "Rs 10,000 is still to pay for your personal training" in (text.json()["text"])
    )

    # Staff at one branch see what's owed there.
    desk = make_staff(gym_a.gym, permissions=["members.view"], branches=[gym_a.branch])
    sign_in(db, client, desk)
    lists = client.get("/api/v1/lists/follow-up").json()
    assert [row["name"] for row in lists["pt_owing"]] == ["Ram Thapa"]


# --- Reports ------------------------------------------------------------------


def test_reports_count_personal_training(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    sign_in(db, client, gym_a.owner)
    assert client.get("/api/v1/reports/monthly").json()["personal_training"] is None

    plan = pt_plan(db, gym_a.gym, price=12_000_00)
    coach = make_staff(gym_a.gym, permissions=["pt.train"])
    sita = make_member(db, gym_a, name="Sita", phone="9800000431")
    hers = sell_pt(db, gym_a, sita, plan, paid=5_000_00, trainer=coach)
    trained(db, hers, TODAY, TODAY)
    trained(db, hers, TODAY, voided=True)  # a mistake, voided: not counted
    ram = make_member(db, gym_a, name="Ram", phone="9800000432")
    trained(db, sell_pt(db, gym_a, ram, plan), TODAY)
    sell(db, gym_a, ram, paid=1500_00)  # a membership: income, not PT's
    other = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(other)
    db.commit()
    hari = make_member(db, gym_a, name="Hari", phone="9800000433")
    sell_pt(db, gym_a, hari, plan, paid=1_000_00, trainer=coach, branch_id=other.id)

    month = client.get("/api/v1/reports/monthly").json()
    pt = month["personal_training"]
    assert (pt["income"], pt["sold"], pt["sessions"], pt["members"]) == (
        6_000_00,
        3,
        3,
        3,
    )
    assert month["income"] == 7_500_00  # PT's is part of it
    assert [(t["name"], t["members"], t["sessions"]) for t in pt["by_trainer"]] == [
        (coach.name, 2, 2),
        (gym_a.owner.name, 1, 1),
    ]

    # Staff with money and reports at one branch: that branch's.
    manager = make_staff(
        gym_a.gym, permissions=["reports.money"], branches=[gym_a.branch]
    )
    sign_in(db, client, manager)
    pt = client.get("/api/v1/reports/monthly").json()["personal_training"]
    assert (pt["income"], pt["sold"], pt["sessions"], pt["members"]) == (
        5_000_00,
        2,
        3,
        2,
    )
