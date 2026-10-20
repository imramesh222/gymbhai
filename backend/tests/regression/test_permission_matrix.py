"""Every permission in PLAN.md §2.1 is enforced (§11).

For each permission: staff holding every permission EXCEPT that one are
refused with a 403 naming it, and staff holding ONLY that one get past the
check. Permissions whose screens belong to a later milestone are listed in
PENDING; the test fails if one is in neither place.
"""

import datetime as dt
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import ALL_PERMISSIONS, Permission
from app.core.time import today_in_nepal
from app.models.staff import StaffUser
from tests.conftest import GymFixture, make_member, priced_plan, sell, sign_in

TODAY = today_in_nepal().isoformat()

# permission -> (method, path, body[, other permissions the action also needs]);
# ids filled from the fixture.
ACTIONS: dict[Permission, tuple] = {
    Permission.MEMBERS_VIEW: ("GET", "/api/v1/members", None),
    Permission.MEMBERS_ADD: (
        "POST",
        "/api/v1/members",
        {"name": "New", "phone": "9800000009"},
    ),
    Permission.MEMBERS_EDIT: ("PATCH", "/api/v1/members/{member}", {"notes": "hi"}),
    Permission.MEMBERS_ARCHIVE: ("POST", "/api/v1/members/{member}/archive", {}),
    Permission.LEADS_MANAGE: (
        "POST",
        "/api/v1/leads",
        {"name": "Asked", "phone": "9800000019"},
    ),
    Permission.MEMBERSHIPS_SELL: (
        "POST",
        "/api/v1/members/{member}/memberships",
        {"plan_id": "{plan}"},
    ),
    Permission.MEMBERSHIPS_EDIT: (
        "PATCH",
        "/api/v1/memberships/{membership}",
        {"discount": 1},
    ),
    Permission.MEMBERSHIPS_EXTEND: (
        "POST",
        "/api/v1/memberships/{membership}/extend",
        {"days": 1, "reason": "test"},
    ),
    Permission.MEMBERSHIPS_EXTEND_ALL: (
        "POST",
        "/api/v1/memberships/extend-all",
        {"days": 1, "reason": "test"},
    ),
    Permission.MEMBERSHIPS_FREEZE: (
        "POST",
        "/api/v1/memberships/{membership}/freeze",
        {"from_date": TODAY, "to_date": TODAY},
    ),
    Permission.MEMBERSHIPS_CANCEL: (
        "POST",
        "/api/v1/memberships/{membership}/cancel",
        {"reason": "test"},
    ),
    Permission.MEMBERSHIPS_DELETE: ("DELETE", "/api/v1/memberships/{membership}", None),
    Permission.PAYMENTS_COLLECT: (
        "POST",
        "/api/v1/payments",
        {"membership_id": "{membership}", "amount": 100, "method": "cash"},
    ),
    Permission.PAYMENTS_EDIT: ("PATCH", "/api/v1/payments/{payment}", {"note": "x"}),
    Permission.PAYMENTS_VOID: (
        "POST",
        "/api/v1/payments/{payment}/void",
        {"reason": "test"},
    ),
    Permission.PAYMENTS_REFUND: (
        "POST",
        "/api/v1/payments/refunds",
        {"membership_id": "{membership}", "amount": 100, "method": "cash"},
    ),
    Permission.REPORTS_MONEY: ("GET", "/api/v1/payments", None),
    Permission.EXPENSES_RECORD: (
        "POST",
        "/api/v1/expenses",
        {"category": "rent", "amount": 100},
    ),
    Permission.EXPENSES_EDIT: ("PATCH", "/api/v1/expenses/{expense}", {"note": "x"}),
    Permission.SETUP_PLANS: (
        "POST",
        "/api/v1/plans",
        {"name": "Day pass", "duration_days": 1},
    ),
    Permission.SETUP_PAYMENT_METHODS: (
        "POST",
        "/api/v1/payment-methods",
        {"kind": "esewa", "label": "eSewa"},
    ),
    Permission.SETUP_CHECK_IN_RULES: (
        "PATCH",
        "/api/v1/gym/check-in-rules",
        {"grace_days": 2},
    ),
    Permission.SETUP_GYM: ("PATCH", "/api/v1/gym", {"address": "Baneshwor"}),
    Permission.STAFF_MANAGE: ("GET", "/api/v1/staff", None),
    Permission.MESSAGES_NOTICES: (
        "POST",
        "/api/v1/notices",
        {"title": "Closed Saturday", "body": "For Tihar."},
    ),
    Permission.MESSAGES_SMS: ("GET", "/api/v1/sms", None),
    Permission.SETUP_REMINDERS: ("GET", "/api/v1/reminder-rules", None),
    Permission.MEMBERS_APP_ACCESS: (
        "PATCH",
        "/api/v1/members/{member}/access",
        {"app_access": True},
    ),
    Permission.PAYMENTS_APPROVE_APP: ("GET", "/api/v1/payment-requests", None),
    Permission.DOOR_CHECK_IN: (
        "POST",
        "/api/v1/check-ins/manual",
        {"member_id": "{member}", "branch_id": "{branch}"},
    ),
    # Letting someone in despite a denial is a manual check-in with override.
    Permission.DOOR_OVERRIDE: (
        "POST",
        "/api/v1/check-ins/manual",
        {
            "member_id": "{member}",
            "branch_id": "{branch}",
            "override": True,
            "note": "x",
        },
        [Permission.DOOR_CHECK_IN],
    ),
    Permission.SETUP_DEVICES: ("GET", "/api/v1/devices", None),
    # Personal training (§18.3): a trainer's own clients, and selling it.
    Permission.PT_TRAIN: ("GET", "/api/v1/pt/clients", None),
    Permission.PT_SELL: (
        "POST",
        "/api/v1/members/{member}/pt",
        {"plan_id": "{pt_plan}", "trainer_id": "{trainer}"},
    ),
    # Classes (§19.4): an instructor's own, booking at the desk, the timetable.
    Permission.CLASSES_TEACH: ("GET", "/api/v1/classes/mine", None),
    Permission.CLASSES_BOOK: (
        "POST",
        "/api/v1/classes/{class}/bookings",
        {"member_id": "{member}"},
    ),
    Permission.CLASSES_MANAGE: ("POST", "/api/v1/class-types", {"name": "Yoga"}),
    # Progress (§19.5).
    Permission.PROGRESS_RECORD: ("GET", "/api/v1/members/{member}/progress", None),
    # The shop (§20.1): a sale, and the products.
    Permission.SHOP_SELL: (
        "POST",
        "/api/v1/sales",
        {"lines": [{"product_id": "{product}", "quantity": 1}]},
    ),
    Permission.SHOP_MANAGE: ("POST", "/api/v1/products", {"name": "Whey", "price": 1}),
}

# Their screens arrive later (PLAN.md §12). Remove each when it gets a route.
PENDING: dict[Permission, str] = {}


def test_every_permission_is_covered_or_pending() -> None:
    assert set(ACTIONS) | set(PENDING) == ALL_PERMISSIONS
    assert not set(ACTIONS) & set(PENDING)


@pytest.fixture
def ids(db: Session, gym_a: GymFixture) -> dict[str, str]:
    from app.models.expense import Expense
    from app.models.training import PtPlan

    member = make_member(db, gym_a)
    plan = priced_plan(db, gym_a.gym)
    membership, payment = sell(db, gym_a, member, plan=plan, paid=500_00)
    expense = Expense(
        gym_id=gym_a.gym.id,
        category="rent",
        amount=25_000_00,
        spent_on=today_in_nepal(),
        method="cash",
    )
    pt_plan = PtPlan(
        gym_id=gym_a.gym.id,
        name="12 sessions",
        kind="sessions",
        sessions=12,
        duration_months=2,
        price=12_000_00,
    )
    from app.core.time import utcnow
    from app.models.classes import ClassType, GymClass

    zumba = ClassType(gym_id=gym_a.gym.id, name="Zumba")
    from app.models.shop import Product

    water = Product(gym_id=gym_a.gym.id, name="Water", category="drink", price=50_00)
    db.add_all([expense, pt_plan, zumba, water])
    db.flush()
    tomorrow = utcnow() + dt.timedelta(days=1)
    gym_class = GymClass(
        gym_id=gym_a.gym.id,
        branch_id=gym_a.branch.id,
        type_id=zumba.id,
        starts_at=tomorrow,
        ends_at=tomorrow + dt.timedelta(hours=1),
        places=10,
    )
    db.add(gym_class)
    db.commit()
    return {
        "class": str(gym_class.id),
        "product": str(water.id),
        "member": str(member.id),
        "plan": str(plan.id),
        "membership": str(membership.id),
        "payment": str(payment.id),
        "branch": str(gym_a.branch.id),
        "expense": str(expense.id),
        "pt_plan": str(pt_plan.id),
        # The owner trains too.
        "trainer": str(gym_a.owner.id),
    }


def _fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


def _call(client: TestClient, permission: Permission, ids: dict[str, str]):
    method, path, body = ACTIONS[permission][:3]
    return client.request(method, _fill(path, ids), json=_fill(body, ids))


@pytest.mark.parametrize("permission", sorted(ACTIONS), ids=lambda p: p.value)
def test_refused_without_it(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
    ids: dict[str, str],
    permission: Permission,
) -> None:
    others = [p.value for p in ALL_PERMISSIONS if p != permission]
    sign_in(db, client, make_staff(gym_a.gym, permissions=others))
    response = _call(client, permission, ids)
    assert response.status_code == 403, response.text
    assert response.json()["permission"] == permission.value


@pytest.mark.parametrize("permission", sorted(ACTIONS), ids=lambda p: p.value)
def test_allowed_with_only_it(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    make_staff: Callable[..., StaffUser],
    ids: dict[str, str],
    permission: Permission,
) -> None:
    also = ACTIONS[permission][3] if len(ACTIONS[permission]) > 3 else []
    granted = [permission.value, *(p.value for p in also)]
    sign_in(db, client, make_staff(gym_a.gym, permissions=granted))
    response = _call(client, permission, ids)
    # Past the permission check. A business rule may still say no (deleting a
    # membership that has payments is a 409), but not a permission one.
    assert response.status_code != 403, response.text
    assert response.status_code < 500, response.text


def test_the_dates_used_are_today() -> None:
    assert dt.date.fromisoformat(TODAY) == today_in_nepal()
