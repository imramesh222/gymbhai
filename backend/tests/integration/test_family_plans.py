"""Family and couple plans: one sale for several people (PLAN.md §19.1).

Everyone has their own membership; the payer's carries the price and every
payment, the others nothing; the door counts the payer's dues for everyone.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal
from app.models.membership import Membership, MembershipGroup
from app.models.messaging import SmsMessage
from app.models.payment import GymPaymentMethod
from app.models.plan import Plan
from app.services import member_auth, receipts, reminders
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal()


def couple_plan(db: Session, gym: GymFixture, *, seats: int = 2, fee: int = 0) -> Plan:
    plan = Plan(
        gym_id=gym.gym.id,
        name="Couple — 1 month" if seats == 2 else "Family — 1 month",
        duration_months=1,
        price=2_500_00,
        admission_fee=fee,
        seats=seats,
    )
    db.add(plan)
    db.commit()
    return plan


@pytest.fixture
def couple(db: Session, gym_a: GymFixture):
    """Ram pays for himself and Sita."""
    ram = make_member(db, gym_a, name="Ram Rai", phone="9812000001")
    sita = make_member(db, gym_a, name="Sita Rai", phone="9812000002")
    return ram, sita, couple_plan(db, gym_a, fee=500_00)


def sell_couple(client: TestClient, payer, plan, others, **extra):
    return client.post(
        f"/api/v1/members/{payer.id}/memberships",
        json={
            "plan_id": str(plan.id),
            "with_member_ids": [str(o.id) for o in others],
            **extra,
        },
    )


def on_plan(db: Session, member) -> Membership:
    return db.scalars(
        select(Membership).where(
            Membership.member_id == member.id, Membership.cancelled_at.is_(None)
        )
    ).one()


# --- selling -----------------------------------------------------------------------


def test_one_sale_one_membership_each_money_on_the_payer(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    response = sell_couple(
        client, ram, plan, [sita], payment={"amount": 1_000_00, "method": "cash"}
    )
    assert response.status_code == 201, response.text
    sold = response.json()["membership"]
    # Both new: the admission fee for each, all on Ram's.
    assert sold["total"] == 2_500_00 + 2 * 500_00
    assert sold["dues"] == 2_500_00
    assert [p["name"] for p in sold["group"]["people"]] == ["Ram Rai", "Sita Rai"]
    assert sold["group"]["payer_name"] == "Ram Rai"

    hers = client.get(f"/api/v1/members/{sita.id}").json()
    assert hers["status"] == "active"
    assert hers["dues"] == 0
    assert hers["group_dues"] == 2_500_00
    [membership] = hers["memberships"]
    assert membership["total"] == 0
    assert membership["group"]["id"] == sold["group"]["id"]
    assert (membership["start_date"], membership["end_date"]) == (
        sold["start_date"],
        sold["end_date"],
    )
    # Owe money lists whoever pays, not everyone on the plan.
    owing = client.get("/api/v1/members?has_dues=true").json()["items"]
    assert [m["name"] for m in owing] == ["Ram Rai"]


def test_the_admission_fee_is_for_newcomers_only(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sell(db, gym_a, ram, paid=1_500_00)  # Ram has been here before
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    assert sold["admission_fee"] == 500_00


def test_a_renewal_starts_each_person_after_their_own_membership(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    ram_now, _ = sell(db, gym_a, ram, paid=1_500_00)
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    assert sold["start_date"] == (ram_now.end_date + dt.timedelta(days=1)).isoformat()
    hers = on_plan(db, sita)
    assert hers.start_date == TODAY


@pytest.mark.parametrize(
    ("people", "code"),
    [("too_many", "too_many_people"), ("twice", "same_person_twice")],
)
def test_who_can_be_on_it(
    client: TestClient, db: Session, gym_a: GymFixture, couple, people, code
) -> None:
    ram, sita, plan = couple
    hari = make_member(db, gym_a, name="Hari Rai", phone="9812000003")
    others = [sita, hari] if people == "too_many" else [sita, sita]
    sign_in(db, client, gym_a.owner)
    response = sell_couple(client, ram, plan, others)
    assert response.status_code == 422
    assert response.json()["code"] == code


def test_a_plan_for_one_takes_nobody_else(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, _ = couple
    sign_in(db, client, gym_a.owner)
    response = sell_couple(client, ram, priced_plan(db, gym_a.gym), [sita])
    assert response.json()["code"] == "plan_for_one"


def test_another_gyms_member_is_not_found(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture, couple
) -> None:
    ram, _, plan = couple
    stranger = make_member(db, gym_b, name="Elsewhere", phone="9812000009")
    sign_in(db, client, gym_a.owner)
    response = sell_couple(client, ram, plan, [stranger])
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert not db.scalars(select(MembershipGroup)).first()


def test_a_double_tap_sells_once(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    headers = {"Idempotency-Key": "couple-1"}
    body = {"plan_id": str(plan.id), "with_member_ids": [str(sita.id)]}
    first = client.post(
        f"/api/v1/members/{ram.id}/memberships", json=body, headers=headers
    )
    again = client.post(
        f"/api/v1/members/{ram.id}/memberships", json=body, headers=headers
    )
    assert first.json() == again.json()
    assert len(db.scalars(select(MembershipGroup)).all()) == 1
    assert len(db.scalars(select(Membership)).all()) == 2


def test_a_plan_for_several_is_never_a_visit_pack(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/plans",
        json={
            "name": "Family 10 visits",
            "duration_months": 1,
            "seats": 3,
            "visit_limit": 10,
        },
    )
    assert response.status_code == 422
    plan = couple_plan(db, gym_a)
    response = client.patch(f"/api/v1/plans/{plan.id}", json={"visit_limit": 10})
    assert response.json()["code"] == "visits_for_one"


# --- the door ----------------------------------------------------------------------


def test_the_dues_rule_counts_the_payers_dues_for_everyone(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    client.patch("/api/v1/gym/check-in-rules", json={"dues_rule": "refuse"})

    def door(member) -> dict:
        return client.post(
            "/api/v1/check-ins/manual",
            json={"member_id": str(member.id), "branch_id": str(gym_a.branch.id)},
        ).json()

    turned_away = door(sita)
    assert turned_away["result"] == "denied_dues"
    assert turned_away["dues"] == sold["dues"]

    paid = client.post(
        "/api/v1/payments",
        json={"membership_id": sold["id"], "amount": sold["dues"], "method": "cash"},
    )
    assert paid.status_code == 201, paid.text
    assert door(sita)["result"] == "allowed"


# --- changes -----------------------------------------------------------------------


def test_add_someone_to_a_free_place(
    client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    family = couple_plan(db, gym_a, seats=3)
    ram = make_member(db, gym_a, name="Ram Rai", phone="9812000001")
    sita = make_member(db, gym_a, name="Sita Rai", phone="9812000002")
    kid = make_member(db, gym_a, name="Kiran Rai", phone="9812000001")
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, family, [sita]).json()["membership"]
    group_id = sold["group"]["id"]

    added = client.post(
        f"/api/v1/membership-groups/{group_id}/members",
        json={"member_id": str(kid.id)},
    )
    assert added.status_code == 200, added.text
    # The payer first, then by name.
    assert [p["name"] for p in added.json()["people"]] == [
        "Ram Rai",
        "Kiran Rai",
        "Sita Rai",
    ]
    theirs = on_plan(db, kid)
    assert (theirs.price, theirs.end_date.isoformat()) == (0, sold["end_date"])
    # The price doesn't change.
    assert client.get(f"/api/v1/memberships/{sold['id']}").json()["total"] == 2_500_00

    full = client.post(
        f"/api/v1/membership-groups/{group_id}/members",
        json={"member_id": str(make_member(db, gym_a, phone="9812000004").id)},
    )
    assert full.json()["code"] == "group_full"
    again = client.post(
        f"/api/v1/membership-groups/{group_id}/members",
        json={"member_id": str(kid.id)},
    )
    assert again.json()["code"] == "already_on_plan"


def test_adding_someone_needs_sell_and_renew(
    client: TestClient, db: Session, gym_a: GymFixture, couple, make_staff
) -> None:
    ram, sita, plan = couple
    sold, _ = sell(db, gym_a, ram, plan=plan)
    viewer = make_staff(gym_a.gym, permissions=["members.view"])
    sign_in(db, client, viewer)
    assert client.get(f"/api/v1/membership-groups/{sold.group_id}").status_code == 200
    response = client.post(
        f"/api/v1/membership-groups/{sold.group_id}/members",
        json={"member_id": str(sita.id)},
    )
    assert response.status_code == 403


def test_removing_someone_leaves_the_payer(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    sell_couple(client, ram, plan, [sita])
    response = client.post(
        f"/api/v1/memberships/{on_plan(db, sita).id}/cancel",
        json={"reason": "moved away"},
    )
    assert response.status_code == 200, response.text
    assert on_plan(db, ram).cancelled_at is None
    group = client.get(f"/api/v1/membership-groups/{on_plan(db, ram).group_id}").json()
    assert [p["cancelled"] for p in group["people"]] == [False, True]


def test_cancelling_the_payers_cancels_everyones(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    client.post(f"/api/v1/memberships/{sold['id']}/cancel", json={"reason": "left"})
    hers = client.get(f"/api/v1/members/{sita.id}").json()
    assert hers["memberships"][0]["status"] == "cancelled"
    history = client.get(f"/api/v1/memberships/{hers['memberships'][0]['id']}/history")
    assert history.json()[0]["reason"] == "left"


def test_the_money_and_the_plan_are_changed_on_the_payers(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    hers = on_plan(db, sita)

    response = client.patch(f"/api/v1/memberships/{hers.id}", json={"price": 100_00})
    assert response.json()["code"] == "money_on_payer"
    # Her dates are hers to change.
    later = (hers.end_date + dt.timedelta(days=3)).isoformat()
    response = client.patch(f"/api/v1/memberships/{hers.id}", json={"end_date": later})
    assert response.status_code == 200

    single = priced_plan(db, gym_a.gym, months=3, price=4_000_00)
    response = client.patch(
        f"/api/v1/memberships/{sold['id']}", json={"plan_id": str(single.id)}
    )
    assert response.json()["code"] == "plan_people_differ"

    longer = Plan(
        gym_id=gym_a.gym.id,
        name="Couple — 3 months",
        duration_months=3,
        price=6_000_00,
        seats=2,
    )
    db.add(longer)
    db.commit()
    response = client.patch(
        f"/api/v1/memberships/{sold['id']}", json={"plan_id": str(longer.id)}
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 6_000_00 + 2 * 500_00
    db.refresh(hers)
    assert hers.plan_name == "Couple — 3 months"
    assert hers.end_date.isoformat() == response.json()["end_date"]


def test_the_payers_is_deleted_last(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sign_in(db, client, gym_a.owner)
    sold = sell_couple(client, ram, plan, [sita]).json()["membership"]
    response = client.delete(f"/api/v1/memberships/{sold['id']}")
    assert response.json()["code"] == "group_has_people"
    assert (
        client.delete(f"/api/v1/memberships/{on_plan(db, sita).id}").status_code == 204
    )
    assert client.delete(f"/api/v1/memberships/{sold['id']}").status_code == 204


# --- messages and receipts ------------------------------------------------------------


def test_expiry_reminders_go_to_whoever_pays(
    db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    end = TODAY + dt.timedelta(days=7)
    sell(
        db,
        gym_a,
        ram,
        plan=plan,
        paid=3_500_00,
        with_member_ids=[sita.id],
        start_date=TODAY - dt.timedelta(days=20),
        end_date=end,
    )
    assert reminders.run_daily(db) == 1
    db.commit()
    [reminder] = db.scalars(select(SmsMessage).where(SmsMessage.kind == "reminder"))
    assert reminder.member_id == ram.id


def test_the_receipt_names_everyone_it_covers(
    db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    _, payment = sell(
        db, gym_a, ram, plan=plan, paid=1_000_00, with_member_ids=[sita.id]
    )
    receipt = receipts.build(db, payment)
    assert receipt.member_name == "Ram Rai"
    assert receipt.covers == ["Sita Rai"]
    assert receipts.pdf(receipt)[:4] == b"%PDF"


# --- the member app ---------------------------------------------------------------


def member_app(client: TestClient, db: Session, member) -> TestClient:
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    return app


def test_each_person_sees_their_own_and_who_pays(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    sell(db, gym_a, ram, plan=plan, paid=1_000_00, with_member_ids=[sita.id])
    hers = member_app(client, db, sita).get("/api/v1/m/me").json()["state"]
    assert hers["plan_with"] == ["Ram Rai"]
    assert hers["paid_by"] == "Ram Rai"
    assert (hers["dues"], hers["group_dues"]) == (0, 2_500_00)
    his = member_app(client, db, ram).get("/api/v1/m/me").json()["state"]
    assert (his["plan_with"], his["paid_by"], his["dues"]) == (
        ["Sita Rai"],
        None,
        2_500_00,
    )


def test_the_payer_renews_it_from_the_app_for_everyone(
    client: TestClient, db: Session, gym_a: GymFixture, couple
) -> None:
    ram, sita, plan = couple
    current, _ = sell(
        db, gym_a, ram, plan=plan, paid=3_500_00, with_member_ids=[sita.id]
    )
    esewa = GymPaymentMethod(gym_id=gym_a.gym.id, kind="esewa", label="eSewa")
    db.add(esewa)
    db.commit()

    his_app = member_app(client, db, ram)
    options = his_app.get("/api/v1/m/renew").json()
    assert plan.name in [p["name"] for p in options["plans"]]
    assert [m["name"] for m in options["renew_with"]] == ["Sita Rai"]
    # Someone else pays for Sita's: no plan for several for her.
    her_options = member_app(client, db, sita).get("/api/v1/m/renew").json()
    assert plan.name not in [p["name"] for p in her_options["plans"]]
    refused = member_app(client, db, sita).post(
        "/api/v1/m/payment-requests",
        json={"plan_id": str(plan.id), "amount": 2_500_00, "transaction_ref": "S-1"},
    )
    assert refused.json()["code"] == "plan_for_group"

    asked = his_app.post(
        "/api/v1/m/payment-requests",
        json={
            "plan_id": str(plan.id),
            "payment_method_id": str(esewa.id),
            "amount": 2_500_00,
            "transaction_ref": "R-1",
        },
    )
    assert asked.status_code == 201, asked.text
    sign_in(db, client, gym_a.owner)
    [waiting] = client.get("/api/v1/payment-requests").json()
    assert waiting["with_names"] == ["Sita Rai"]
    assert waiting["expected_total"] == 2_500_00  # nobody new: no admission fee
    approved = client.post(f"/api/v1/payment-requests/{waiting['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    renewed = db.scalars(
        select(Membership).where(
            Membership.member_id == sita.id, Membership.id != on_plan_first(db, sita)
        )
    ).one()
    assert renewed.start_date == current.end_date + dt.timedelta(days=1)
    assert renewed.group_id is not None and renewed.group_id != current.group_id


def on_plan_first(db: Session, member):
    return db.scalars(
        select(Membership.id)
        .where(Membership.member_id == member.id)
        .order_by(Membership.start_date)
    ).first()
