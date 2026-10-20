"""One gym can never read or change another gym's data (PLAN.md §3, §11).

Signed in as gym A's owner — who holds every permission — every attempt on
gym B's records by id must be a 404, not a 403, which would confirm the id
exists. Every route that takes an id must be listed in CROSS_GYM_ROUTES;
`test_every_id_route_is_covered` fails until it is.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_in_nepal, utcnow
from app.models.classes import ClassSlot, ClassType, GymClass
from app.models.expense import Expense
from app.models.gym import Gym
from app.models.lead import Lead
from app.models.member_app import Device, FreezeRequest, PaymentRequest
from app.models.messaging import Notice, ReminderRule
from app.models.payment import GymPaymentMethod
from app.models.plan import Plan
from app.models.platform import MemberImport
from app.models.progress import ProgressEntry
from app.models.training import PtPackage, PtPlan, PtSession
from app.services import classes as classes_service
from app.services import memberships as ms
from app.services import sessions
from tests.conftest import (
    GymFixture,
    context_for,
    make_member,
    sell,
    sign_in,
)
from tests.routes import all_routes

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@dataclass
class World:
    """Gym B, with one of everything."""

    ids: dict[str, Any]


@pytest.fixture
def world_b(db: Session, gym_b: GymFixture, make_staff) -> World:
    member = make_member(db, gym_b, phone="9819999999")
    membership, payment = sell(db, gym_b, member, paid=500_00)
    freeze = ms.freeze(
        db,
        context_for(db, gym_b.owner),
        membership,
        membership.end_date,
        membership.end_date,
        "injury",
    )
    method = GymPaymentMethod(gym_id=gym_b.gym.id, kind="esewa", label="eSewa")
    notice = Notice(
        gym_id=gym_b.gym.id, title="B only", body="Secret", published_at=utcnow()
    )
    db.add_all([method, notice])
    rule = db.scalars(
        select(ReminderRule).where(ReminderRule.gym_id == gym_b.gym.id)
    ).first()
    staff = make_staff(gym_b.gym)
    b_session = sessions.start(db, staff, None).session
    device = Device(
        gym_id=gym_b.gym.id,
        branch_id=gym_b.branch.id,
        name="B door",
        token_hash="b" * 64,
    )
    b_request = PaymentRequest(
        gym_id=gym_b.gym.id,
        member_id=member.id,
        plan_id=membership.plan_id,
        amount=1500_00,
        status="pending",
    )
    b_import = MemberImport(
        gym_id=gym_b.gym.id, filename="b.csv", headers=["Name"], rows=[["Ram"]]
    )
    b_freeze_request = FreezeRequest(
        gym_id=gym_b.gym.id,
        member_id=member.id,
        membership_id=membership.id,
        from_date=membership.start_date,
        to_date=membership.start_date,
        reason="Away",
    )
    b_lead = Lead(
        gym_id=gym_b.gym.id,
        branch_id=gym_b.branch.id,
        name="B enquiry",
        phone="9819999990",
        source="walk_in",
    )
    b_expense = Expense(
        gym_id=gym_b.gym.id,
        branch_id=gym_b.branch.id,
        category="rent",
        amount=30_000_00,
        spent_on=today_in_nepal(),
        method="bank",
    )
    b_pt_plan = PtPlan(
        gym_id=gym_b.gym.id,
        name="B monthly PT",
        kind="monthly",
        duration_months=1,
        price=8_000_00,
    )
    db.add_all(
        [device, b_request, b_import, b_freeze_request, b_lead, b_expense, b_pt_plan]
    )
    db.flush()
    b_package = PtPackage(
        gym_id=gym_b.gym.id,
        member_id=member.id,
        plan_id=b_pt_plan.id,
        plan_name=b_pt_plan.name,
        kind="monthly",
        trainer_id=gym_b.owner.id,
        branch_id=gym_b.branch.id,
        start_date=today_in_nepal(),
        end_date=today_in_nepal() + dt.timedelta(days=29),
        price=8_000_00,
        discount=0,
    )
    db.add(b_package)
    db.flush()
    b_session = PtSession(
        gym_id=gym_b.gym.id,
        package_id=b_package.id,
        trained_on=today_in_nepal(),
        trainer_id=gym_b.owner.id,
    )
    db.add(b_session)
    db.commit()
    # A couple plan (§19.1), sold to the member and one more.
    couple = Plan(
        gym_id=gym_b.gym.id, name="B couple", duration_months=1, price=2_500_00, seats=2
    )
    db.add(couple)
    db.commit()
    partner = make_member(db, gym_b, name="B partner", phone="9819999998")
    shared, _ = sell(db, gym_b, member, plan=couple, with_member_ids=[partner.id])
    # Classes (§19.4): a type, the timetable, a class tomorrow with a booking.
    b_type = ClassType(gym_id=gym_b.gym.id, name="B Zumba")
    db.add(b_type)
    db.flush()
    b_slot = ClassSlot(
        gym_id=gym_b.gym.id,
        branch_id=gym_b.branch.id,
        type_id=b_type.id,
        weekday=(today_in_nepal() + dt.timedelta(days=1)).weekday(),
        starts="07:00",
        minutes=60,
        places=10,
    )
    db.add(b_slot)
    db.flush()
    classes_service.generate(db, slot_id=b_slot.id)
    b_class = db.scalars(select(GymClass).where(GymClass.slot_id == b_slot.id)).first()
    b_booking = classes_service.book(db, db.get(Gym, gym_b.gym.id), member, b_class)
    # Progress (§19.5).
    b_entry = ProgressEntry(
        gym_id=gym_b.gym.id,
        member_id=member.id,
        measured_on=today_in_nepal(),
        weight_g=70_000,
        recorded_by=gym_b.owner.id,
    )
    db.add(b_entry)
    # The shop (§20.1): a product, and a sale of it.
    from app.services import shop as shop_service

    b_ctx = context_for(db, gym_b.owner)
    b_product = shop_service.create_product(
        db, b_ctx, {"name": "B whey", "category": "supplement", "price": 100_00,
                    "stock": 5}, None,
    )  # fmt: skip
    b_sale, _ = shop_service.sell(
        db, b_ctx, lines=[(b_product.id, 1)], member_id=None, branch_id=None,
        discount=0, method="cash", transaction_ref=None, note=None,
    )  # fmt: skip
    db.commit()
    return World(
        ids={
            "branch_id": gym_b.branch.id,
            "staff_id": staff.id,
            "session_id": b_session.id,
            "plan_id": membership.plan_id,
            "method_id": method.id,
            "member_id": member.id,
            "membership_id": membership.id,
            "freeze_id": freeze.id,
            "payment_id": payment.id,
            "rule_id": rule.id,
            "notice_id": notice.id,
            "device_id": device.id,
            "request_id": b_request.id,
            "freeze_request_id": b_freeze_request.id,
            "lead_id": b_lead.id,
            "import_id": b_import.id,
            "expense_id": b_expense.id,
            "pt_plan_id": b_pt_plan.id,
            "package_id": b_package.id,
            "pt_session_id": b_session.id,
            "group_id": shared.group_id,
            "type_id": b_type.id,
            "slot_id": b_slot.id,
            "class_id": b_class.id,
            "booking_id": b_booking.id,
            "entry_id": b_entry.id,
            "product_id": b_product.id,
            "sale_id": b_sale.id,
        }
    )


TODAY = dt.date.today().isoformat()

# (method, path, JSON body or "upload")
CROSS_GYM_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/v1/branches/{branch_id}", None),
    ("PATCH", "/api/v1/branches/{branch_id}", {"name": "Taken"}),
    ("PATCH", "/api/v1/staff/{staff_id}", {"name": "Taken"}),
    ("POST", "/api/v1/staff/{staff_id}/password", {"new_password": "taken-over-123"}),
    ("POST", "/api/v1/staff/{staff_id}/two-step/reset", None),
    ("POST", "/api/v1/staff/{staff_id}/sign-out", None),
    ("POST", "/api/v1/members/{member_id}/erase", None),
    # Not gym data, but the same rule: another account's device is not found.
    ("POST", "/api/v1/auth/sessions/{session_id}/sign-out", None),
    ("PATCH", "/api/v1/plans/{plan_id}", {"price": 1}),
    ("PATCH", "/api/v1/payment-methods/{method_id}", {"label": "Taken"}),
    ("POST", "/api/v1/payment-methods/{method_id}/qr", "upload"),
    (
        "PUT",
        "/api/v1/payment-methods/{method_id}/gateway",
        {"merchant": "X", "secret_key": "abcd1234"},
    ),
    ("DELETE", "/api/v1/payment-methods/{method_id}/gateway", None),
    ("GET", "/api/v1/members/{member_id}", None),
    ("PATCH", "/api/v1/members/{member_id}", {"name": "Taken"}),
    ("POST", "/api/v1/members/{member_id}/archive", {}),
    ("POST", "/api/v1/members/{member_id}/unarchive", None),
    ("POST", "/api/v1/members/{member_id}/photo", "upload"),
    ("POST", "/api/v1/members/{member_id}/memberships", "own_plan"),
    ("GET", "/api/v1/members/{member_id}/history", None),
    ("GET", "/api/v1/memberships/{membership_id}", None),
    ("PATCH", "/api/v1/memberships/{membership_id}", {"discount": 1}),
    (
        "POST",
        "/api/v1/memberships/{membership_id}/extend",
        {"days": 1, "reason": "why not"},
    ),
    (
        "POST",
        "/api/v1/memberships/{membership_id}/freeze",
        {"from_date": TODAY, "to_date": TODAY},
    ),
    ("POST", "/api/v1/memberships/{membership_id}/freezes/{freeze_id}/end", None),
    ("POST", "/api/v1/memberships/{membership_id}/cancel", {"reason": "taken over"}),
    ("DELETE", "/api/v1/memberships/{membership_id}", None),
    ("GET", "/api/v1/memberships/{membership_id}/history", None),
    ("PATCH", "/api/v1/payments/{payment_id}", {"note": "taken"}),
    ("POST", "/api/v1/payments/{payment_id}/void", {"reason": "taken over"}),
    ("GET", "/api/v1/payments/{payment_id}/receipt", None),
    ("POST", "/api/v1/payments/{payment_id}/receipt/printed", None),
    ("PATCH", "/api/v1/expenses/{expense_id}", {"amount": 1}),
    ("POST", "/api/v1/expenses/{expense_id}/void", {"reason": "taken over"}),
    ("POST", "/api/v1/members/{member_id}/sms", {"body": "Hello"}),
    ("GET", "/api/v1/members/{member_id}/message", None),
    ("PATCH", "/api/v1/reminder-rules/{rule_id}", {"enabled": False}),
    ("DELETE", "/api/v1/reminder-rules/{rule_id}", None),
    ("DELETE", "/api/v1/notices/{notice_id}", None),
    ("POST", "/api/v1/devices/{device_id}/revoke", None),
    ("POST", "/api/v1/payment-requests/{request_id}/approve", {}),
    ("POST", "/api/v1/payment-requests/{request_id}/reject", {"reason": "taken over"}),
    ("POST", "/api/v1/freeze-requests/{freeze_request_id}/approve", None),
    (
        "POST",
        "/api/v1/freeze-requests/{freeze_request_id}/reject",
        {"reason": "taken over"},
    ),
    ("POST", "/api/v1/payments/{payment_id}/receipt-link", None),
    ("POST", "/api/v1/payments/{payment_id}/receipt-whatsapp", None),
    ("GET", "/api/v1/leads/{lead_id}", None),
    ("PATCH", "/api/v1/leads/{lead_id}", {"name": "Taken"}),
    ("POST", "/api/v1/leads/{lead_id}/trial", None),
    ("PATCH", "/api/v1/members/{member_id}/access", {"app_access": False}),
    ("POST", "/api/v1/members/{member_id}/sign-out-all", None),
    ("POST", "/api/v1/members/{member_id}/resend-welcome", None),
    ("POST", "/api/v1/members/{member_id}/sign-in-link", None),
    ("POST", "/api/v1/members/{member_id}/qr/reissue", None),
    ("POST", "/api/v1/members/{member_id}/card/reissue", None),
    ("GET", "/api/v1/members/{member_id}/card", None),
    ("POST", "/api/v1/members/import/{import_id}/preview", {}),
    ("POST", "/api/v1/members/import/{import_id}/commit", {}),
    ("PATCH", "/api/v1/pt/plans/{pt_plan_id}", {"price": 1}),
    ("GET", "/api/v1/members/{member_id}/pt", None),
    ("POST", "/api/v1/members/{member_id}/pt", "own_pt_plan"),
    ("PATCH", "/api/v1/pt/packages/{package_id}", {"start_date": TODAY}),
    ("POST", "/api/v1/pt/packages/{package_id}/cancel", {"reason": "taken over"}),
    ("POST", "/api/v1/pt/packages/{package_id}/sessions", {}),
    ("POST", "/api/v1/pt/sessions/{pt_session_id}/void", {"reason": "taken over"}),
    ("GET", "/api/v1/membership-groups/{group_id}", None),
    ("POST", "/api/v1/membership-groups/{group_id}/members", "own_member"),
    ("PATCH", "/api/v1/class-types/{type_id}", {"name": "Taken"}),
    ("PATCH", "/api/v1/class-slots/{slot_id}", {"starts": "05:00"}),
    ("GET", "/api/v1/classes/{class_id}", None),
    ("PATCH", "/api/v1/classes/{class_id}", {"places": 1}),
    ("POST", "/api/v1/classes/{class_id}/cancel", {"reason": "taken over"}),
    ("POST", "/api/v1/classes/{class_id}/bookings", "own_member"),
    ("POST", "/api/v1/class-bookings/{booking_id}/cancel", None),
    ("POST", "/api/v1/class-bookings/{booking_id}/attended", {"came": True}),
    ("GET", "/api/v1/members/{member_id}/classes", None),
    ("GET", "/api/v1/members/{member_id}/progress", None),
    ("POST", "/api/v1/members/{member_id}/progress", {"weight_g": 60_000}),
    ("PUT", "/api/v1/members/{member_id}/progress/height", {"height_mm": 1700}),
    ("PATCH", "/api/v1/progress/{entry_id}", {"weight_g": 60_000}),
    ("DELETE", "/api/v1/progress/{entry_id}", None),
    ("PATCH", "/api/v1/products/{product_id}", {"name": "Taken"}),
    ("POST", "/api/v1/products/{product_id}/stock", {"kind": "restock", "quantity": 1}),
    ("GET", "/api/v1/products/{product_id}/stock", None),
    ("POST", "/api/v1/sales/{sale_id}/void", {"reason": "taken over"}),
]

# Id routes whose permission is not the gym at all.
NOT_GYM_SCOPED = {
    ("GET", "/api/v1/files/{key}"),
    # The signed link is the permission (app/core/signed_links.py).
    ("GET", "/api/v1/receipts/{payment_id}.pdf"),
    # Public, by the gym's own address.
    ("GET", "/api/v1/m/{slug}/gym"),
    ("GET", "/api/v1/m/{slug}/logo"),
    ("POST", "/api/v1/m/{slug}/otp/request"),
    ("POST", "/api/v1/m/{slug}/otp/verify"),
    ("POST", "/api/v1/m/{slug}/desk-sign-in"),
    ("GET", "/api/v1/m/{slug}/join"),
    ("POST", "/api/v1/m/{slug}/join"),
    # Not an id: which export (members, payments, ...), of the caller's gym.
    ("GET", "/api/v1/export/{kind}.xlsx"),
    # Platform admin: every gym, by design (test_platform_admin.py).
    ("GET", "/api/v1/admin/gyms/{gym_id}"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/subscription"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/sms-credits"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/suspend"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/unsuspend"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/owner-password"),
    ("POST", "/api/v1/admin/gyms/{gym_id}/owner-two-step"),
    ("POST", "/api/v1/admin/subscription-payments/{payment_id}/approve"),
    ("POST", "/api/v1/admin/subscription-payments/{payment_id}/reject"),
    ("PATCH", "/api/v1/admin/apps/{app_id}"),
    ("GET", "/api/v1/admin/apps/{app_id}/build"),
    ("PATCH", "/api/v1/admin/plans/{plan_id}"),
    ("PATCH", "/api/v1/admin/changelog/{entry_id}"),
    ("DELETE", "/api/v1/admin/changelog/{entry_id}"),
    ("POST", "/api/v1/admin/gym-referrals/{referral_id}/reward"),
    ("POST", "/api/v1/admin/gym-referrals/{referral_id}/reject"),
    # The member's own records: tests/regression/test_member_isolation.py.
    ("POST", "/api/v1/m/payment-requests/{request_id}/screenshot"),
    ("POST", "/api/v1/m/payment-requests/{request_id}/withdraw"),
    # tests/integration/test_online_payments.py: another member's is not found.
    ("GET", "/api/v1/m/online-payments/{payment_id}"),
    ("POST", "/api/v1/m/online-payments/{payment_id}/check"),
    # The checkout page's signed link is the permission (§20.2).
    ("GET", "/api/v1/pay/{token}"),
    ("POST", "/api/v1/pay/{token}/check"),
    ("POST", "/api/v1/pay/{token}/pretend"),
    ("POST", "/api/v1/m/me/payments/{payment_id}/receipt-link"),
    ("POST", "/api/v1/m/freeze-requests/{freeze_request_id}/withdraw"),
    # tests/integration/test_member_devices.py: another member's is not found.
    ("POST", "/api/v1/m/me/sessions/{session_id}/sign-out"),
    ("POST", "/api/v1/m/classes/{class_id}/book"),
    ("POST", "/api/v1/m/class-bookings/{booking_id}/cancel"),
    ("PATCH", "/api/v1/m/progress/{entry_id}"),
    ("DELETE", "/api/v1/m/progress/{entry_id}"),
    ("PATCH", "/api/v1/m/progress/photos/{photo_id}"),
    ("DELETE", "/api/v1/m/progress/photos/{photo_id}"),
}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    CROSS_GYM_ROUTES,
    ids=[f"{m} {p}" for m, p, _ in CROSS_GYM_ROUTES],
)
def test_another_gyms_record_is_not_found(
    client: TestClient,
    db: Session,
    gym_a: GymFixture,
    world_b: World,
    method: str,
    path: str,
    body: Any,
) -> None:
    sign_in(db, client, gym_a.owner)
    url = path.format(**world_b.ids)
    if body == "upload":
        response = client.request(
            method, url, files={"file": ("x.png", PNG, "image/png")}
        )
    elif body == "own_plan":
        # Gym A's own plan, gym B's member: still not found.
        from tests.conftest import priced_plan

        plan = priced_plan(db, gym_a.gym)
        response = client.request(method, url, json={"plan_id": str(plan.id)})
    elif body == "own_member":
        # Gym A's own member, gym B's family plan: still not found.
        mine = make_member(db, gym_a, name="A member", phone="9811111111")
        response = client.request(method, url, json={"member_id": str(mine.id)})
    elif body == "own_pt_plan":
        # Gym A's own PT plan and trainer, gym B's member: still not found.
        pt_plan = PtPlan(
            gym_id=gym_a.gym.id,
            name="A monthly PT",
            kind="monthly",
            duration_months=1,
            price=8_000_00,
        )
        db.add(pt_plan)
        db.commit()
        response = client.request(
            method,
            url,
            json={"plan_id": str(pt_plan.id), "trainer_id": str(gym_a.owner.id)},
        )
    else:
        response = client.request(method, url, json=body)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "not_found"


def test_every_id_route_is_covered() -> None:
    covered = {(m, p) for m, p, _ in CROSS_GYM_ROUTES} | NOT_GYM_SCOPED
    for method, path, _ in all_routes():
        if "{" in path:
            assert (method, path) in covered, (
                f"{method} {path} takes an id: add it to CROSS_GYM_ROUTES"
            )


def test_nothing_of_gym_b_changed(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    """Run every attempt, then check gym B's rows are exactly as they were."""
    from app.models.member import Member
    from app.models.membership import Membership
    from app.models.payment import Payment

    member = db.get(Member, world_b.ids["member_id"])
    membership = db.get(Membership, world_b.ids["membership_id"])
    before = (member.name, membership.end_date, membership.discount)
    sign_in(db, client, gym_a.owner)
    for method, path, body in CROSS_GYM_ROUTES:
        if body not in ("upload", "own_plan", "own_pt_plan"):
            client.request(method, path.format(**world_b.ids), json=body)
    for row in (member, membership):
        db.refresh(row)
    assert (member.name, membership.end_date, membership.discount) == before
    assert membership.cancelled_at is None
    assert db.get(Payment, world_b.ids["payment_id"]).voided_at is None
    expense = db.get(Expense, world_b.ids["expense_id"])
    db.refresh(expense)
    assert (expense.amount, expense.voided_at) == (30_000_00, None)
    package = db.get(PtPackage, world_b.ids["package_id"])
    db.refresh(package)
    assert (package.start_date, package.cancelled_at) == (today_in_nepal(), None)
    sessions = db.scalars(
        select(PtSession).where(PtSession.package_id == package.id)
    ).all()
    assert [s.voided_at for s in sessions] == [None]
    assert db.get(PtPlan, world_b.ids["pt_plan_id"]).price == 8_000_00
    from app.models.shop import Product, ProductSale

    product = db.get(Product, world_b.ids["product_id"])
    db.refresh(product)
    assert (product.name, product.stock) == ("B whey", 4)
    sale = db.get(ProductSale, world_b.ids["sale_id"])
    db.refresh(sale)
    assert sale.voided_at is None


def test_lists_only_show_your_own_gym(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    sign_in(db, client, gym_a.owner)
    assert {b["id"] for b in client.get("/api/v1/branches").json()} == {
        str(gym_a.branch.id)
    }
    assert client.get("/api/v1/gym").json()["id"] == str(gym_a.gym.id)
    assert client.get("/api/v1/members").json()["total"] == 0
    assert client.get("/api/v1/payments").json()["total"] == 0
    # The shop (§20.1): gym B's product and its walk-in sale stay gym B's.
    assert client.get("/api/v1/products?include_hidden=true").json() == []
    sales = client.get("/api/v1/sales").json()
    assert (sales["items"], sales["total"]) == ([], 0)
    expenses = client.get("/api/v1/expenses").json()
    assert (expenses["items"], expenses["sum_amount"]) == ([], 0)
    assert client.get("/api/v1/reports/monthly").json()["expenses"] == 0
    assert client.get("/api/v1/payment-methods").json() == []
    assert client.get("/api/v1/notices").json() == []
    assert client.get("/api/v1/sms").json()["items"] == []
    assert client.get("/api/v1/lists/follow-up").json() == {
        "due_today": [],
        "due_this_week": [],
        "lapsed": [],
        "owing": [],
        "owing_total": 0,
        "pt_owing": [],  # gym B's member owes on personal training
        "pt_owing_total": 0,
        "not_visiting": [],
        "not_visiting_total": 0,
        "not_visiting_days": 14,
    }
    plan_ids = {p["id"] for p in client.get("/api/v1/plans").json()}
    assert str(world_b.ids["plan_id"]) not in plan_ids
    staff = client.get("/api/v1/staff").json()
    assert [s["id"] for s in staff] == [str(gym_a.owner.id)]
    # Personal training: plans, trainers and clients are the gym's own.
    assert client.get("/api/v1/pt/plans?include_hidden=true").json() == []
    assert [t["id"] for t in client.get("/api/v1/pt/trainers").json()] == [
        str(gym_a.owner.id)
    ]
    assert client.get("/api/v1/pt/packages").json() == []
    assert client.get("/api/v1/pt/clients").json() == []
    # Reports' PT figures: none of gym B's sale, session or trainer.
    db.add(
        PtPlan(
            gym_id=gym_a.gym.id,
            name="A monthly PT",
            kind="monthly",
            duration_months=1,
            price=8_000_00,
        )
    )
    db.commit()
    assert client.get("/api/v1/reports/monthly").json()["personal_training"] == {
        "income": 0,
        "sold": 0,
        "sessions": 0,
        "members": 0,
        "by_trainer": [],
    }
    # Phone lookups too: another gym's member is never "already on file".
    assert client.get("/api/v1/members/phone-check?phone=9819999999").json() == []


def test_extend_everyone_stays_in_your_gym(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    from app.models.membership import Membership

    membership = db.get(Membership, world_b.ids["membership_id"])
    end = membership.end_date
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/memberships/extend-all", json={"days": 7, "reason": "Dashain"}
    )
    assert response.json() == {"extended": 0}
    db.refresh(membership)
    assert membership.end_date == end


def test_selling_another_gyms_plan_is_refused(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    member = make_member(db, gym_a)
    sign_in(db, client, gym_a.owner)
    response = client.post(
        f"/api/v1/members/{member.id}/memberships",
        json={"plan_id": str(world_b.ids["plan_id"])},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bad_plan"


def test_paying_into_another_gyms_membership_is_not_found(
    client: TestClient, db: Session, gym_a: GymFixture, world_b: World
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.post(
        "/api/v1/payments",
        json={
            "membership_id": str(world_b.ids["membership_id"]),
            "amount": 100,
            "method": "cash",
        },
    )
    assert response.status_code == 404


def test_a_gym_id_in_the_body_is_refused_not_obeyed(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    sign_in(db, client, gym_a.owner)
    response = client.patch(
        "/api/v1/gym", json={"gym_id": str(gym_b.gym.id), "name": "Hijacked"}
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/members",
        json={"name": "X", "phone": "9811111111", "gym_id": str(gym_b.gym.id)},
    )
    assert response.status_code == 422
    assert db.get(Gym, gym_b.gym.id).name == "Gym iron-house"


def test_a_token_is_bound_to_its_gym(
    client: TestClient, db: Session, gym_a: GymFixture, gym_b: GymFixture
) -> None:
    """Moving an account to another gym invalidates the tokens it holds."""
    sign_in(db, client, gym_a.owner)
    gym_a.owner.gym_id = gym_b.gym.id
    gym_a.owner.is_owner = False
    db.commit()
    assert client.get("/api/v1/gym").status_code == 401
