"""Personal training (PLAN.md §18.3): plans, selling it, trainers and their
sessions, and its money."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.calendar import plan_end_date
from app.core.time import today_in_nepal
from app.models.gym import Branch, Gym
from app.models.payment import Payment
from app.models.training import PtPackage, PtPlan, PtSession
from app.services import live, member_auth
from tests.conftest import GymFixture, make_member, sell, sign_in
from tests.integration.test_receipts import path_of

TODAY = today_in_nepal()
CODE = "123456"


def pt_plan(
    db: Session,
    gym: Gym,
    *,
    kind: str = "sessions",
    sessions: int | None = 12,
    months: int = 2,
    price: int = 12_000_00,
    name: str | None = None,
) -> PtPlan:
    plan = PtPlan(
        gym_id=gym.id,
        name=name or (f"{sessions} sessions" if kind == "sessions" else "Monthly PT"),
        kind=kind,
        sessions=sessions if kind == "sessions" else None,
        duration_months=months,
        price=price,
    )
    db.add(plan)
    db.commit()
    return plan


def sell_pt(client: TestClient, member_id, plan: PtPlan, trainer_id, **extra) -> dict:
    """Sold through the API, as the desk does: the package's detail."""
    response = client.post(
        f"/api/v1/members/{member_id}/pt",
        json={"plan_id": str(plan.id), "trainer_id": str(trainer_id), **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()["package"]


def record(client: TestClient, package_id: str, **body):
    return client.post(f"/api/v1/pt/packages/{package_id}/sessions", json=body)


@pytest.fixture
def trainer(make_staff, gym_a: GymFixture):
    return make_staff(gym_a.gym, permissions=["pt.train", "members.view"])


# --- plans ------------------------------------------------------------------------


def test_plans_for_packs_and_for_months(
    client: TestClient, db: Session, gym_a: GymFixture
):
    sign_in(db, client, gym_a.owner)
    pack = client.post(
        "/api/v1/pt/plans",
        json={
            "name": "12 sessions",
            "kind": "sessions",
            "sessions": 12,
            "duration_months": 2,
            "price": 12_000_00,
        },
    )
    assert pack.status_code == 201, pack.text
    monthly = client.post(
        "/api/v1/pt/plans",
        json={
            "name": "Monthly PT",
            "kind": "monthly",
            "duration_months": 1,
            "price": 8_000_00,
        },
    )
    assert monthly.status_code == 201, monthly.text
    # A pack says how many sessions; monthly training doesn't count them.
    no_count = {"name": "x", "kind": "sessions", "duration_months": 1, "price": 1}
    assert client.post("/api/v1/pt/plans", json=no_count).status_code == 422
    counted = {**no_count, "kind": "monthly", "sessions": 4}
    assert client.post("/api/v1/pt/plans", json=counted).status_code == 422

    # Hidden: no longer sold, still in its settings.
    client.patch(f"/api/v1/pt/plans/{monthly.json()['id']}", json={"is_active": False})
    assert [p["name"] for p in client.get("/api/v1/pt/plans").json()] == ["12 sessions"]
    assert len(client.get("/api/v1/pt/plans?include_hidden=true").json()) == 2

    # A pack made monthly drops its count; made a pack again, it needs one.
    pack_url = f"/api/v1/pt/plans/{pack.json()['id']}"
    assert client.patch(pack_url, json={"kind": "monthly"}).json()["sessions"] is None
    refused = client.patch(pack_url, json={"kind": "sessions"})
    assert (refused.status_code, refused.json()["code"]) == (422, "pack_sessions")
    back = client.patch(pack_url, json={"kind": "sessions", "sessions": 10})
    assert (back.json()["kind"], back.json()["sessions"]) == ("sessions", 10)


def test_plans_are_set_up_by_plans_and_prices(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    body = {"name": "x", "kind": "monthly", "duration_months": 1, "price": 1}
    sign_in(db, client, make_staff(gym_a.gym, permissions=["pt.sell"]))
    # The desk sees them to sell them, and changes nothing.
    assert client.get("/api/v1/pt/plans").status_code == 200
    refused = client.post("/api/v1/pt/plans", json=body)
    assert refused.json()["permission"] == "setup.plans"
    sign_in(db, client, make_staff(gym_a.gym, permissions=["setup.plans"]))
    assert client.post("/api/v1/pt/plans", json=body).status_code == 201
    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert client.get("/api/v1/pt/plans").json()["permission"] == "pt.sell"


# --- selling ----------------------------------------------------------------------


def test_selling_a_pack_with_part_payment(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/members/{member.id}/pt",
        json={
            "plan_id": str(plan.id),
            "trainer_id": str(gym_a.owner.id),
            "discount": 1_000_00,
            "payment": {"amount": 5_000_00, "method": "cash"},
        },
    )
    assert response.status_code == 201, response.text
    package, payment = response.json()["package"], response.json()["payment"]
    assert (package["plan_name"], package["kind"], package["sessions"]) == (
        "12 sessions",
        "sessions",
        12,
    )
    assert (package["status"], package["sessions_left"]) == ("active", 12)
    assert package["trainer_name"] == gym_a.owner.name
    assert package["start_date"] == TODAY.isoformat()
    # Two months in the gym's own calendar, as for memberships.
    end = plan_end_date(
        TODAY, months=2, days=None, calendar=gym_a.gym.config.plan_months
    )
    assert package["end_date"] == end.isoformat()
    assert (package["total"], package["paid"], package["dues"]) == (
        11_000_00,
        5_000_00,
        6_000_00,
    )
    assert (payment["pt_package_id"], payment["membership_id"]) == (
        package["id"],
        None,
    )

    # Its own money: the membership's dues never count it.
    detail = client.get(f"/api/v1/members/{member.id}").json()
    assert detail["dues"] == 0
    assert [p["amount"] for p in detail["payments"]] == [5_000_00]
    listed = client.get(f"/api/v1/members/{member.id}/pt").json()
    assert [p["id"] for p in listed] == [package["id"]]
    assert [p["amount"] for p in listed[0]["payments"]] == [5_000_00]


def test_what_was_sold_keeps_its_terms(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, plan, gym_a.owner.id)
    client.patch(
        f"/api/v1/pt/plans/{plan.id}",
        json={"name": "10 sessions", "sessions": 10, "price": 15_000_00},
    )
    again = client.get(f"/api/v1/members/{member.id}/pt").json()[0]
    assert (again["plan_name"], again["sessions"], again["total"]) == (
        package["plan_name"],
        12,
        12_000_00,
    )


def test_a_sale_needs_a_trainer_and_an_offered_plan(
    client: TestClient, db: Session, gym_a: GymFixture, trainer, make_staff
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    desk = make_staff(gym_a.gym, permissions=["pt.sell"])
    away = make_staff(gym_a.gym, permissions=["pt.train"], is_active=False)
    sign_in(db, client, gym_a.owner)
    # Staff who train members, and the owner, who has every permission.
    names = [t["name"] for t in client.get("/api/v1/pt/trainers").json()]
    assert names == [gym_a.owner.name, trainer.name]
    for who in (desk, away):
        refused = client.post(
            f"/api/v1/members/{member.id}/pt",
            json={"plan_id": str(plan.id), "trainer_id": str(who.id)},
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "bad_trainer")

    plan.is_active = False
    db.commit()
    hidden = client.post(
        f"/api/v1/members/{member.id}/pt",
        json={"plan_id": str(plan.id), "trainer_id": str(trainer.id)},
    )
    assert hidden.json()["code"] == "plan_hidden"

    client.post(f"/api/v1/members/{member.id}/archive", json={})
    plan.is_active = True
    db.commit()
    archived = client.post(
        f"/api/v1/members/{member.id}/pt",
        json={"plan_id": str(plan.id), "trainer_id": str(trainer.id)},
    )
    assert (archived.status_code, archived.json()["code"]) == (409, "member_archived")


def test_selling_twice_with_one_key_sells_once(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    body = {
        "plan_id": str(plan.id),
        "trainer_id": str(gym_a.owner.id),
        "payment": {"amount": 12_000_00, "method": "cash"},
    }
    headers = {"Idempotency-Key": "pt-sale-0001"}
    first = client.post(f"/api/v1/members/{member.id}/pt", json=body, headers=headers)
    again = client.post(f"/api/v1/members/{member.id}/pt", json=body, headers=headers)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    assert db.scalar(select(func.count()).select_from(PtPackage)) == 1
    assert db.scalar(select(func.count()).select_from(Payment)) == 1


# --- sessions ---------------------------------------------------------------------


def test_a_pack_holds_so_many_sessions(
    client: TestClient, db: Session, gym_a: GymFixture, trainer
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym, sessions=2)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, plan, trainer.id)

    sign_in(db, client, trainer)
    first = record(client, package["id"], note="Legs")
    assert first.status_code == 201, first.text
    assert first.json()["sessions_left"] == 1
    logged = first.json()["session_log"][0]
    assert (logged["trainer_name"], logged["note"]) == (trainer.name, "Legs")
    assert logged["trained_on"] == TODAY.isoformat()
    second = record(client, package["id"]).json()
    assert (second["status"], second["sessions_left"]) == ("used_up", 0)
    full = record(client, package["id"])
    assert (full.status_code, full.json()["code"]) == (409, "pt_used_up")

    # A mistake is voided with a reason, never deleted: its session is free.
    mistake = second["session_log"][0]["id"]
    voided = client.post(
        f"/api/v1/pt/sessions/{mistake}/void", json={"reason": "Didn't come"}
    ).json()
    assert (voided["status"], voided["sessions_left"]) == ("active", 1)
    assert [s["void_reason"] for s in voided["session_log"]] == ["Didn't come", None]
    again = client.post(f"/api/v1/pt/sessions/{mistake}/void", json={"reason": "x2x"})
    assert again.json()["code"] == "session_voided"
    assert record(client, package["id"]).status_code == 201


def test_monthly_training_counts_attendance_without_a_limit(
    client: TestClient, db: Session, gym_a: GymFixture, trainer
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym, kind="monthly", months=1, price=8_000_00)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, plan, trainer.id)
    sign_in(db, client, trainer)
    for _ in range(3):
        last = record(client, package["id"])
        assert last.status_code == 201
    body = last.json()
    assert (body["sessions"], body["sessions_used"], body["sessions_left"]) == (
        None,
        3,
        None,
    )
    assert body["status"] == "active" and body["last_session_on"] == TODAY.isoformat()


def test_a_session_falls_within_its_dates(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    soon = sell_pt(
        client, member.id, plan, gym_a.owner.id, start_date=str(TODAY + dt.timedelta(1))
    )
    assert soon["status"] == "upcoming"
    early = record(client, soon["id"])
    assert (early.status_code, early.json()["code"]) == (422, "outside_dates")

    begun = sell_pt(
        client,
        member.id,
        plan,
        gym_a.owner.id,
        start_date=str(TODAY - dt.timedelta(days=10)),
    )
    before = record(client, begun["id"], trained_on=str(TODAY - dt.timedelta(11)))
    assert before.json()["code"] == "outside_dates"
    future = record(client, begun["id"], trained_on=str(TODAY + dt.timedelta(1)))
    assert future.json()["code"] == "future_date"
    # Trained yesterday, recorded today.
    late = record(client, begun["id"], trained_on=str(TODAY - dt.timedelta(1)))
    assert late.json()["last_session_on"] == str(TODAY - dt.timedelta(1))


def test_only_their_trainer_or_the_desk_records(
    client: TestClient, db: Session, gym_a: GymFixture, trainer, make_staff
):
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    other_trainer = make_staff(gym_a.gym, permissions=["pt.train"])
    desk = make_staff(gym_a.gym, permissions=["pt.sell"])
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, plan, trainer.id)

    sign_in(db, client, other_trainer)
    refused = record(client, package["id"])
    assert (refused.status_code, refused.json()["permission"]) == (403, "pt.sell")

    # The desk records it for the trainer, who trained them.
    sign_in(db, client, desk)
    by_desk = record(client, package["id"]).json()["session_log"][0]
    assert (by_desk["trainer_name"], by_desk["recorded_by_name"]) == (
        trainer.name,
        desk.name,
    )

    sign_in(db, client, other_trainer)
    void_url = f"/api/v1/pt/sessions/{by_desk['id']}/void"
    assert client.post(void_url, json={"reason": "Not mine"}).status_code == 403
    sign_in(db, client, trainer)
    assert client.post(void_url, json={"reason": "Twice"}).status_code == 200

    sign_in(db, client, make_staff(gym_a.gym, permissions=["members.view"]))
    assert record(client, package["id"]).json()["permission"] == "pt.train"


def test_recording_twice_with_one_key_records_once(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, pt_plan(db, gym_a.gym), gym_a.owner.id)
    headers = {"Idempotency-Key": "pt-session-0001"}
    url = f"/api/v1/pt/packages/{package['id']}/sessions"
    client.post(url, json={}, headers=headers)
    assert client.post(url, json={}, headers=headers).json()["sessions_used"] == 1
    assert db.scalar(select(func.count()).select_from(PtSession)) == 1


# --- the trainers' lists -----------------------------------------------------------


def test_a_trainers_own_clients_still_to_train(
    client: TestClient, db: Session, gym_a: GymFixture, trainer, make_staff
):
    sita = make_member(db, gym_a)
    ram = make_member(db, gym_a, name="Ram Thapa", phone="9812345679")
    plan = pt_plan(db, gym_a.gym)
    one = pt_plan(db, gym_a.gym, sessions=1)
    other_trainer = make_staff(gym_a.gym, permissions=["pt.train"])
    sign_in(db, client, gym_a.owner)
    active = sell_pt(client, sita.id, plan, trainer.id)
    upcoming = sell_pt(
        client, ram.id, plan, trainer.id, start_date=str(TODAY + dt.timedelta(5))
    )
    used_up = sell_pt(client, ram.id, one, trainer.id)
    record(client, used_up["id"])
    sell_pt(  # ended
        client,
        sita.id,
        plan,
        trainer.id,
        start_date=str(TODAY - dt.timedelta(60)),
        end_date=str(TODAY - dt.timedelta(30)),
    )
    cancelled = sell_pt(client, sita.id, plan, trainer.id)
    client.post(
        f"/api/v1/pt/packages/{cancelled['id']}/cancel", json={"reason": "Changed mind"}
    )
    elsewhere = sell_pt(client, ram.id, plan, other_trainer.id)
    record(client, active["id"])

    sign_in(db, client, trainer)
    mine = client.get("/api/v1/pt/clients").json()
    assert [p["id"] for p in mine] == [active["id"], upcoming["id"]]
    assert (mine[0]["member_name"], mine[0]["last_session_on"]) == (
        "Sita Rai",
        TODAY.isoformat(),
    )
    assert client.get("/api/v1/pt/packages").json()["permission"] == "pt.sell"

    sign_in(db, client, gym_a.owner)
    everyone = {p["id"] for p in client.get("/api/v1/pt/packages").json()}
    assert everyone == {active["id"], upcoming["id"], elsewhere["id"]}
    theirs = client.get(f"/api/v1/pt/packages?trainer_id={other_trainer.id}").json()
    assert [p["id"] for p in theirs] == [elsewhere["id"]]


def test_branch_limited_staff_see_their_branch(
    client: TestClient, db: Session, gym_a: GymFixture, make_staff
):
    koteshwor = Branch(gym_id=gym_a.gym.id, name="Koteshwor")
    db.add(koteshwor)
    db.commit()
    member = make_member(db, gym_a)
    plan = pt_plan(db, gym_a.gym)
    sign_in(db, client, gym_a.owner)
    here = sell_pt(
        client,
        member.id,
        plan,
        gym_a.owner.id,
        payment={"amount": 1_000_00, "method": "cash"},
    )
    there = sell_pt(
        client,
        member.id,
        plan,
        gym_a.owner.id,
        branch_id=str(koteshwor.id),
        payment={"amount": 2_000_00, "method": "cash"},
    )

    staff = make_staff(
        gym_a.gym,
        permissions=["pt.sell", "reports.money", "members.view"],
        branches=[koteshwor],
    )
    sign_in(db, client, staff)
    assert [p["id"] for p in client.get("/api/v1/pt/packages").json()] == [there["id"]]
    payments = client.get("/api/v1/payments").json()
    assert [p["amount"] for p in payments["items"]] == [2_000_00]
    gone = client.patch(f"/api/v1/pt/packages/{here['id']}", json={})
    assert gone.status_code == 404


# --- changing and cancelling -------------------------------------------------------


def test_another_trainer_or_other_dates(
    client: TestClient, db: Session, gym_a: GymFixture, trainer
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, pt_plan(db, gym_a.gym), gym_a.owner.id)
    url = f"/api/v1/pt/packages/{package['id']}"
    moved = client.patch(url, json={"trainer_id": str(trainer.id), "reason": "Shift"})
    assert moved.json()["trainer_name"] == trainer.name

    record(client, package["id"])
    later = client.patch(url, json={"start_date": str(TODAY + dt.timedelta(1))})
    assert (later.status_code, later.json()["code"]) == (409, "sessions_outside")
    backwards = client.patch(url, json={"end_date": str(TODAY - dt.timedelta(1))})
    assert (backwards.status_code, backwards.json()["code"]) == (422, "bad_dates")

    history = client.get(f"/api/v1/members/{member.id}/history").json()
    changed = next(h for h in history if h["action"] == "pt.updated")
    assert changed["changes"]["trainer_id"] == {
        "before": str(gym_a.owner.id),
        "after": str(trainer.id),
    }
    assert changed["reason"] == "Shift"


def test_cancelling_with_a_refund(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(
        client,
        member.id,
        pt_plan(db, gym_a.gym),
        gym_a.owner.id,
        payment={"amount": 5_000_00, "method": "cash"},
    )
    url = f"/api/v1/pt/packages/{package['id']}"
    cancelled = client.post(
        f"{url}/cancel",
        json={
            "reason": "Moved to Pokhara",
            "refund": {"amount": 2_000_00, "method": "cash"},
        },
    ).json()
    assert (cancelled["status"], cancelled["paid"], cancelled["dues"]) == (
        "cancelled",
        3_000_00,
        0,
    )
    assert [p["kind"] for p in cancelled["payments"]] == ["payment", "refund"]

    pay = client.post(
        "/api/v1/payments",
        json={"pt_package_id": package["id"], "amount": 100, "method": "cash"},
    )
    assert (pay.status_code, pay.json()["code"]) == (409, "pt_cancelled")
    assert record(client, package["id"]).json()["code"] == "pt_cancelled"
    assert client.patch(url, json={"trainer_id": None}).json()["code"] == "pt_cancelled"
    again = client.post(f"{url}/cancel", json={"reason": "Again"})
    assert again.json()["code"] == "pt_cancelled"


# --- money -------------------------------------------------------------------------


def test_collecting_money_for_it(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, pt_plan(db, gym_a.gym), gym_a.owner.id)
    assert package["dues"] == 12_000_00

    paid = client.post(
        "/api/v1/payments",
        json={
            "pt_package_id": package["id"],
            "amount": 2_000_00,
            "method": "esewa",
            "transaction_ref": "ESW-PT-1",
        },
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["pt_package_id"] == package["id"]
    too_much = client.post(
        "/api/v1/payments",
        json={"pt_package_id": package["id"], "amount": 10_000_01, "method": "cash"},
    )
    assert (too_much.json()["code"], too_much.json()["owed"]) == (
        "overpayment",
        10_000_00,
    )
    membership, _ = sell(db, gym_a, member)
    for wrong in (
        {"pt_package_id": package["id"], "membership_id": str(membership.id)},
        {},
    ):
        both = client.post(
            "/api/v1/payments", json={**wrong, "amount": 100, "method": "cash"}
        )
        assert both.status_code == 422

    receipt = client.get(f"/api/v1/payments/{paid.json()['id']}/receipt").json()
    assert receipt["training"] is True
    assert (receipt["plan_name"], receipt["start_date"]) == (
        "12 sessions",
        TODAY.isoformat(),
    )
    assert (receipt["membership_total"], receipt["dues_after"]) == (
        12_000_00,
        10_000_00,
    )
    link = client.post(f"/api/v1/payments/{paid.json()['id']}/receipt-link").json()
    pdf = client.get(path_of(link["url"]))
    assert pdf.headers["content-type"] == "application/pdf"

    # Edited and voided like any payment, its dues following.
    edited = client.patch(
        f"/api/v1/payments/{paid.json()['id']}",
        json={"amount": 3_000_00, "reason": "Typed wrong"},
    )
    assert edited.status_code == 200
    detail = client.get(f"/api/v1/members/{member.id}/pt").json()[0]
    assert detail["dues"] == 9_000_00
    client.post(
        f"/api/v1/payments/{paid.json()['id']}/void", json={"reason": "Bounced"}
    )
    assert client.get(f"/api/v1/members/{member.id}/pt").json()[0]["dues"] == 12_000_00

    history = client.get(f"/api/v1/members/{member.id}/history").json()
    actions = {h["action"] for h in history}
    assert {"pt.sold", "payment.recorded", "payment.updated", "payment.voided"} <= (
        actions
    )


def test_money_reports_count_it(client: TestClient, db: Session, gym_a: GymFixture):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    sell_pt(
        client,
        member.id,
        pt_plan(db, gym_a.gym),
        gym_a.owner.id,
        payment={"amount": 4_000_00, "method": "cash"},
    )
    assert client.get("/api/v1/dashboard/today").json()["collected"] == 4_000_00
    assert client.get("/api/v1/reports/monthly").json()["income"] == 4_000_00
    payments = client.get("/api/v1/payments").json()
    assert (payments["total"], payments["sum_amount"]) == (1, 4_000_00)


def test_a_payment_for_another_gyms_training_is_not_found(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
):
    member = make_member(db, gym_b, phone="9819999999")
    sign_in(db, client, gym_b.owner)
    package = sell_pt(client, member.id, pt_plan(db, gym_b.gym), gym_b.owner.id)
    sign_in(db, client, gym_a.owner)
    for path in ("/api/v1/payments", "/api/v1/payments/refunds"):
        response = client.post(
            path,
            json={"pt_package_id": package["id"], "amount": 100, "method": "cash"},
        )
        assert response.status_code == 404, response.text


# --- the member, their history, and erasing them ------------------------------------


def test_the_member_sees_it_in_the_app(
    client: TestClient, db: Session, gym_a: GymFixture, trainer, monkeypatch
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(
        client,
        member.id,
        pt_plan(db, gym_a.gym),
        trainer.id,
        payment={"amount": 2_000_00, "method": "cash"},
    )
    record(client, package["id"])
    used_up = sell_pt(client, member.id, pt_plan(db, gym_a.gym, sessions=1), trainer.id)
    record(client, used_up["id"])

    monkeypatch.setattr(member_auth.secrets, "randbelow", lambda n: int(CODE))
    client.headers.pop("Authorization")
    client.post("/api/v1/m/fitness-zone/otp/request", json={"phone": member.phone})
    me = client.post(
        "/api/v1/m/fitness-zone/otp/verify", json={"phone": member.phone, "code": CODE}
    ).json()["me"]
    # A used-up pack is done; what's left to train is shown.
    assert me["training"] == [
        {
            "id": package["id"],
            "plan_name": "12 sessions",
            "kind": "sessions",
            "status": "active",
            "trainer_name": trainer.name,
            "start_date": package["start_date"],
            "end_date": package["end_date"],
            "sessions": 12,
            "sessions_left": 11,
            "days_left": package["days_left"],
            "dues": 10_000_00,
        }
    ]
    assert me["state"]["dues"] == 0


def test_erasing_a_member_clears_their_session_notes(
    client: TestClient, db: Session, gym_a: GymFixture
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(
        client,
        member.id,
        pt_plan(db, gym_a.gym),
        gym_a.owner.id,
        payment={"amount": 2_000_00, "method": "cash"},
    )
    record(client, package["id"], note="Knee pain, go easy")
    assert client.post(f"/api/v1/members/{member.id}/erase").status_code == 200
    session = db.scalars(select(PtSession)).one()
    db.refresh(session)
    assert session.note is None
    # The gym's accounts stay.
    assert db.scalar(select(func.count()).select_from(PtPackage)) == 1
    assert db.scalar(select(func.count()).select_from(Payment)) == 1


def test_screens_hear_about_it(
    client: TestClient, db: Session, gym_a: GymFixture, monkeypatch
):
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    package = sell_pt(client, member.id, pt_plan(db, gym_a.gym), gym_a.owner.id)
    heard: list[str] = []
    monkeypatch.setattr(
        live, "publish", lambda db, **event: heard.append(event["kind"])
    )
    record(client, package["id"])
    client.post(
        "/api/v1/payments",
        json={"pt_package_id": package["id"], "amount": 100, "method": "cash"},
    )
    # The member's page and app, and the Personal training screens: each time.
    assert heard == [live.MEMBER, live.PT, live.MEMBER, live.PT]
