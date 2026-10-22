"""Lists cost the same number of queries for one row as for many (no N+1).

Each test loads a list with one row, adds more rows, and loads it again: the
number of SQL statements must not grow with the rows.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.billing import PlatformPlan
from app.models.plan import PlanBranch
from app.models.platform import SubscriptionPayment
from app.services import payment_requests as requests_service
from tests.conftest import (
    GymFixture,
    make_gym,
    make_member,
    priced_plan,
    sell,
    sign_in,
)

MORE = 5


@contextmanager
def counting(engine: sa.Engine) -> Generator[list[str]]:
    statements: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)


def queries(engine: sa.Engine, fetch: Callable[[], object]) -> int:
    with counting(engine) as statements:
        fetch()
    return len(statements)


def same_cost(engine: sa.Engine, client: TestClient, url: str, add: Callable) -> None:
    def get() -> list:
        response = client.get(url)
        assert response.status_code == 200, response.text
        return response.json()

    one = queries(engine, get)
    before = len(get())
    for n in range(MORE):
        add(n)
    assert len(get()) == before + MORE
    many = queries(engine, get)
    assert many == one, f"{url}: {one} queries for {before} rows, {many} for more"


def test_payment_requests(engine, client: TestClient, db: Session, gym_a) -> None:
    sign_in(db, client, gym_a.owner)
    plan = priced_plan(db, gym_a.gym)

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123400{n:02d}")
        if n % 2:
            sell(db, gym_a, member)  # some renewing, some first-time
        requests_service.create(
            db,
            member,
            plan_id=plan.id,
            payment_method_id=None,
            amount=plan.price,
            transaction_ref=f"REF{n}",
        )
        db.commit()

    add(99)
    same_cost(engine, client, "/api/v1/payment-requests", add)


def test_plans(engine, client: TestClient, db: Session, gym_a: GymFixture) -> None:
    sign_in(db, client, gym_a.owner)
    plan = priced_plan(db, gym_a.gym)

    def add(n: int) -> None:
        from app.models.plan import Plan

        one_branch = Plan(
            gym_id=gym_a.gym.id,
            name=f"Branch plan {n}",
            duration_months=1,
            all_branches=False,
        )
        db.add(one_branch)
        db.flush()
        db.add(PlanBranch(plan_id=one_branch.id, branch_id=gym_a.branch.id))
        db.commit()

    plan.all_branches = False
    db.add(PlanBranch(plan_id=plan.id, branch_id=gym_a.branch.id))
    db.commit()
    same_cost(engine, client, "/api/v1/plans", add)


def test_staff(engine, client: TestClient, db: Session, gym_a, make_staff) -> None:
    sign_in(db, client, gym_a.owner)

    def add(n: int) -> None:
        make_staff(gym_a.gym, branches=[gym_a.branch])

    same_cost(engine, client, "/api/v1/staff", add)


def test_admin_gyms(engine, client: TestClient, db: Session, platform_admin) -> None:
    sign_in(db, client, platform_admin)
    plan = PlatformPlan(name="Basic", monthly_price=1000_00, max_active_members=100)
    db.add(plan)
    db.commit()

    def add(n: int) -> None:
        fixture = make_gym(db, slug=f"count-gym-{n}", phone=f"98415000{n:02d}")
        member = make_member(db, fixture)
        sell(db, fixture, member)
        db.add(
            SubscriptionPayment(
                gym_id=fixture.gym.id,
                kind="subscription",
                platform_plan_id=plan.id,
                months=1,
                amount=1000_00,
                transaction_ref=f"SUB{n}",
                status="pending",
            )
        )
        db.commit()

    add(99)
    same_cost(engine, client, "/api/v1/admin/gyms", add)
    same_cost(
        engine,
        client,
        "/api/v1/admin/subscription-payments",
        lambda n: add(n + 10),
    )


def test_importing_a_register(engine, client: TestClient, db: Session, gym_a) -> None:
    """Committing a register of thousands must not mean thousands of trips."""
    sign_in(db, client, gym_a.owner)

    def commit(rows: int) -> int:
        register = "Name,Mobile,Expiry\n" + "".join(
            f"Member {n},98{rows:02d}{n:06d},2026-12-01\n" for n in range(rows)
        )
        preview = client.post(
            "/api/v1/members/import",
            files={"file": ("register.csv", register.encode(), "text/csv")},
        ).json()
        url = f"/api/v1/members/import/{preview['id']}/commit"
        with counting(engine) as statements:
            done = client.post(url, json={}).json()
        assert done["result"]["created"] == rows, done
        return len(statements)

    assert commit(1) == commit(1 + MORE * 10)


def test_today(engine, client: TestClient, db: Session, gym_a: GymFixture) -> None:
    """Today's to-do lists and charts cost the same however many are on them."""
    import datetime as dt

    from app.core.time import today_in_nepal
    from app.services import checkins

    today = today_in_nepal()

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Due {n}", phone=f"98100002{n:02d}")
        sell(
            db,
            gym_a,
            member,
            paid=100_00,
            start_date=today - dt.timedelta(days=29),
            end_date=today,
        )
        checkins.check_in(
            db, gym=gym_a.gym, member=member, branch_id=gym_a.branch.id, method="manual"
        )
        db.commit()

    sign_in(db, client, gym_a.owner)
    add(99)

    def get() -> dict:
        response = client.get("/api/v1/dashboard/today")
        assert response.status_code == 200, response.text
        return response.json()

    one = queries(engine, get)
    for n in range(MORE):
        add(n)
    body = get()
    assert len(body["ending_today"]) == MORE + 1
    assert body["check_ins"] == MORE + 1
    assert queries(engine, get) == one


def test_members_list(
    engine, client: TestClient, db: Session, gym_a: GymFixture
) -> None:
    """The table's states, dues and last visits come batched, not per row."""
    from app.services import checkins

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98100003{n:02d}")
        sell(db, gym_a, member, paid=100_00)
        checkins.check_in(
            db, gym=gym_a.gym, member=member, branch_id=gym_a.branch.id, method="manual"
        )
        db.commit()

    sign_in(db, client, gym_a.owner)
    add(99)

    def get() -> list:
        response = client.get("/api/v1/members?sort=last_visit&direction=desc")
        assert response.status_code == 200, response.text
        return response.json()["items"]

    one = queries(engine, get)
    for n in range(MORE):
        add(n)
    assert len(get()) == MORE + 1
    assert queries(engine, get) == one


def test_follow_up(engine, client: TestClient, db: Session, gym_a: GymFixture) -> None:
    import datetime as dt

    from app.core.time import today_in_nepal, utcnow

    sign_in(db, client, gym_a.owner)
    today = today_in_nepal()

    def add(n: int) -> None:
        # Owing, not visiting, and (every other one) ending this week.
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123500{n:02d}")
        member.created_at = utcnow() - dt.timedelta(days=60)
        end = today + dt.timedelta(days=3 if n % 2 else 20)
        sell(db, gym_a, member, start_date=today - dt.timedelta(days=5), end_date=end)

    def get() -> dict:
        response = client.get("/api/v1/lists/follow-up")
        assert response.status_code == 200, response.text
        return response.json()

    add(90)
    one = queries(engine, get)
    for n in range(MORE):
        add(n)
    lists = get()
    assert len(lists["owing"]) == len(lists["not_visiting"]) == MORE + 1
    many = queries(engine, get)
    assert many == one, f"follow up: {one} queries for one member, {many} for more"


def test_freeze_requests(engine, client: TestClient, db: Session, gym_a) -> None:
    import datetime as dt

    from app.core.time import today_in_nepal
    from app.services import freeze_requests

    sign_in(db, client, gym_a.owner)
    today = today_in_nepal()

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123600{n:02d}")
        sell(
            db, gym_a, member, start_date=today, end_date=today + dt.timedelta(days=29)
        )
        freeze_requests.create(
            db,
            member,
            from_date=today + dt.timedelta(days=2),
            to_date=today + dt.timedelta(days=5),
            reason="Away",
        )
        db.commit()

    add(90)
    same_cost(engine, client, "/api/v1/freeze-requests", add)


def test_expenses(engine, client: TestClient, db: Session, gym_a, make_staff) -> None:
    """Who recorded each one comes in one query, however many there are."""
    from app.core.time import today_in_nepal
    from app.models.expense import Expense

    sign_in(db, client, gym_a.owner)

    def add(n: int) -> None:
        db.add(
            Expense(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id if n % 2 else None,
                category="salaries",
                amount=(n + 1) * 1000_00,
                spent_on=today_in_nepal(),
                method="cash",
                paid_to=f"Trainer {n}",
                created_by=make_staff(gym_a.gym).id,
            )
        )
        db.commit()

    add(90)

    def get() -> list:
        response = client.get("/api/v1/expenses")
        assert response.status_code == 200, response.text
        return response.json()["items"]

    one = queries(engine, get)
    for n in range(MORE):
        add(n)
    assert len(get()) == MORE + 1
    assert queries(engine, get) == one


def test_leads(engine, client: TestClient, db: Session, gym_a) -> None:
    from app.models.lead import Lead

    sign_in(db, client, gym_a.owner)
    plan = priced_plan(db, gym_a.gym)
    referrer = make_member(db, gym_a, name="Referrer", phone="9812370000")

    def add(n: int) -> None:
        db.add(
            Lead(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id,
                name=f"Lead {n}",
                phone=f"98123700{n:02d}",
                source="referral",
                plan_id=plan.id,
                assigned_to=gym_a.owner.id,
                referred_by_id=referrer.id,
            )
        )
        db.commit()

    add(90)
    same_cost(engine, client, "/api/v1/leads", add)


def test_personal_training(engine, client: TestClient, db: Session, gym_a) -> None:
    """Sessions, money and names come in a few queries, however many packages
    and sessions (PLAN.md §18.3): the trainers' lists and the member's tab."""
    from app.models.training import PtPlan

    member = make_member(db, gym_a)
    plan = PtPlan(
        gym_id=gym_a.gym.id,
        name="12 sessions",
        kind="sessions",
        sessions=12,
        duration_months=2,
        price=12_000_00,
    )
    db.add(plan)
    db.commit()
    sign_in(db, client, gym_a.owner)

    def add(n: int) -> None:
        sold = client.post(
            f"/api/v1/members/{member.id}/pt",
            json={
                "plan_id": str(plan.id),
                "trainer_id": str(gym_a.owner.id),
                "payment": {"amount": (n + 1) * 100_00, "method": "cash"},
            },
        )
        assert sold.status_code == 201, sold.text
        package = sold.json()["package"]["id"]
        for _ in range(2):
            recorded = client.post(f"/api/v1/pt/packages/{package}/sessions", json={})
            assert recorded.status_code == 201, recorded.text

    add(90)
    same_cost(engine, client, "/api/v1/pt/packages", add)
    same_cost(engine, client, f"/api/v1/members/{member.id}/pt", add)


def test_personal_training_owed_and_reported(
    engine, client: TestClient, db: Session, gym_a, make_staff
) -> None:
    """Follow up's personal training list and Reports' PT figures cost the
    same however many packages, trainers and sessions (PLAN.md §18.3)."""
    from app.models.training import PtPlan

    plan = PtPlan(
        gym_id=gym_a.gym.id,
        name="12 sessions",
        kind="sessions",
        sessions=12,
        duration_months=2,
        price=12_000_00,
    )
    db.add(plan)
    db.commit()
    sign_in(db, client, gym_a.owner)

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Client {n}", phone=f"98123600{n:02d}")
        coach = make_staff(gym_a.gym, permissions=["pt.train"])
        sold = client.post(
            f"/api/v1/members/{member.id}/pt",
            json={
                "plan_id": str(plan.id),
                "trainer_id": str(coach.id),
                "payment": {"amount": 100_00, "method": "cash"},
            },
        )
        assert sold.status_code == 201, sold.text
        package = sold.json()["package"]["id"]
        recorded = client.post(f"/api/v1/pt/packages/{package}/sessions", json={})
        assert recorded.status_code == 201, recorded.text

    def get(url: str) -> dict:
        response = client.get(url)
        assert response.status_code == 200, response.text
        return response.json()

    follow_up, report = "/api/v1/lists/follow-up", "/api/v1/reports/monthly"
    add(90)
    owed = queries(engine, lambda: get(follow_up))
    reported = queries(engine, lambda: get(report))
    for n in range(MORE):
        add(n)
    assert len(get(follow_up)["pt_owing"]) == MORE + 1
    assert len(get(report)["personal_training"]["by_trainer"]) == MORE + 1
    assert queries(engine, lambda: get(follow_up)) == owed
    assert queries(engine, lambda: get(report)) == reported


def test_who_gets_a_staff_notification(engine, db: Session, gym_a, make_staff) -> None:
    """Worked out in the same few queries however many staff take them (§18.6)."""
    from app.services import sessions
    from app.services.push import staff as staff_push

    def add(n: int) -> None:
        person = make_staff(gym_a.gym, permissions=["memberships.freeze"])
        staff_push.subscribe(
            db,
            person,
            sessions.start(db, person, None).session,
            endpoint=f"https://push.example.com/staff/{n}",
            p256dh="B" * 87,
            auth="a" * 22,
            user_agent=None,
        )
        db.commit()

    def who() -> list:
        # By branch, as a freeze request goes: the costlier way.
        return staff_push.recipients(
            db, gym_a.gym.id, staff_push.FREEZE_REQUEST, gym_a.branch.id
        )

    add(90)
    one = queries(engine, who)
    for n in range(MORE):
        add(n)
    assert len(who()) == MORE + 1
    assert queries(engine, who) == one


def test_door_readers(engine, client: TestClient, db: Session, gym_a) -> None:
    """A reader's members and changes waiting come in one query for every
    reader on the list; what a reader should hold costs the same however many
    members (§18.2)."""
    from app.models.member_app import Device
    from app.services import readers

    sign_in(db, client, gym_a.owner)

    def add_reader(n: int) -> None:
        made = client.post(
            "/api/v1/devices/readers",
            json={
                "kind": "zkteco",
                "name": f"Reader {n}",
                "branch_id": str(gym_a.branch.id),
                "serial": f"SERIAL{n:04d}",
            },
        )
        assert made.status_code == 201, made.text

    add_reader(90)
    same_cost(engine, client, "/api/v1/devices", add_reader)

    device = db.scalars(sa.select(Device).where(Device.serial == "SERIAL0090")).one()
    plan = priced_plan(db, gym_a.gym)

    def add_member(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98000099{n:02d}")
        sell(db, gym_a, member, plan=plan, paid=1500_00)

    add_member(90)
    one = queries(engine, lambda: readers.wanted(db, device))
    for n in range(MORE):
        add_member(n)
    assert len(readers.wanted(db, device)) == MORE + 1
    assert queries(engine, lambda: readers.wanted(db, device)) == one


def test_kiosk_roster(engine, client: TestClient, db: Session, gym_a) -> None:
    """The kiosk's roster (PLAN.md §19.2): fourteen days of state per member,
    from the same few queries."""
    sign_in(db, client, gym_a.owner)
    token = client.post(
        "/api/v1/devices", json={"branch_id": str(gym_a.branch.id), "name": "Door"}
    ).json()["token"]
    door = TestClient(client.app)
    door.headers["X-Device-Token"] = token

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123400{n:02d}")
        sell(db, gym_a, member, paid=500_00 * (n % 2))

    def get() -> list:
        response = door.get("/api/v1/kiosk/roster")
        assert response.status_code == 200, response.text
        return response.json()["members"]

    add(99)
    one = queries(engine, get)
    for n in range(MORE):
        add(n)
    assert len(get()) == 1 + MORE
    assert queries(engine, get) == one


def test_classes(engine, client: TestClient, db: Session, gym_a) -> None:
    """A week of classes with their counts (PLAN.md §19.4)."""
    import datetime as dt

    from app.core.time import utcnow
    from app.models.classes import ClassBooking, ClassType, GymClass

    sign_in(db, client, gym_a.owner)
    kind = ClassType(gym_id=gym_a.gym.id, name="Zumba")
    db.add(kind)
    db.commit()

    def add(n: int) -> None:
        start = utcnow() + dt.timedelta(days=1, hours=n)
        row = GymClass(
            gym_id=gym_a.gym.id,
            branch_id=gym_a.branch.id,
            type_id=kind.id,
            starts_at=start,
            ends_at=start + dt.timedelta(hours=1),
            places=5,
            instructor_id=gym_a.owner.id,
        )
        db.add(row)
        db.flush()
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123400{n:02d}")
        db.add(
            ClassBooking(
                gym_id=gym_a.gym.id,
                class_id=row.id,
                member_id=member.id,
                status="booked",
                booked_at=utcnow(),
            )
        )
        db.commit()

    add(99)
    same_cost(engine, client, "/api/v1/classes", add)


def test_the_members_week_of_classes(engine, client: TestClient, db: Session, gym_a):
    """The member app's timetable reads the member once, not once a class
    (PLAN.md §19.4): a busy week costs what a quiet one does."""
    import datetime as dt

    from app.core.time import utcnow
    from app.models.classes import ClassType, GymClass
    from app.services import member_auth

    member = make_member(db, gym_a, name="Sita Rai", phone="9812349999")
    sell(db, gym_a, member, paid=1500_00)
    kind = ClassType(gym_id=gym_a.gym.id, name="Yoga")
    db.add(kind)
    db.commit()
    issued = member_auth.start_session(db, member, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"

    def add(n: int) -> None:
        # A different day each: every one of them was asked about before.
        start = utcnow() + dt.timedelta(hours=3 + 22 * n)
        db.add(
            GymClass(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id,
                type_id=kind.id,
                starts_at=start,
                ends_at=start + dt.timedelta(hours=1),
                places=5,
            )
        )
        db.commit()

    def week() -> list:
        response = app.get("/api/v1/m/classes")
        assert response.status_code == 200, response.text
        return response.json()["classes"]

    add(0)
    one = queries(engine, week)
    for n in range(1, MORE + 1):
        add(n)
    assert len(week()) == 1 + MORE
    assert queries(engine, week) == one


def test_messages_and_automations(engine, client: TestClient, db: Session, gym_a):
    """Sent messages with WhatsApp rows among the SMS, and the automations
    with their WhatsApp wording (§19.3)."""
    from app.core.whatsapp_templates import WhatsApp
    from app.models.messaging import ReminderRule
    from app.services.sms import service as sms
    from app.services.whatsapp import service as whatsapp

    sign_in(db, client, gym_a.owner)
    gym_a.gym.settings = {**gym_a.gym.settings, "whatsapp": True}
    db.commit()

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123500{n:02d}")
        if n % 2:
            whatsapp.queue(
                db,
                gym_a.gym,
                member,
                WhatsApp("welcome_no_plan", {"name": "M", "gym": "G"}),
                kind="welcome",
                fallback="Welcome",
            )
        else:
            sms.queue(
                db, gym_id=gym_a.gym.id, to=member.phone, body="Hi", kind="manual"
            )
        db.add(
            ReminderRule(
                gym_id=gym_a.gym.id, trigger="dues", days=20 + n, template="Owed"
            )
        )
        db.commit()

    def log() -> list:
        return client.get("/api/v1/sms").json()["items"]

    add(99)
    one = queries(engine, log)
    rules_one = queries(engine, lambda: client.get("/api/v1/reminder-rules"))
    before = len(log())
    for n in range(MORE):
        add(n)
    assert len(log()) == before + MORE
    assert queries(engine, log) == one
    assert queries(engine, lambda: client.get("/api/v1/reminder-rules")) == rules_one


def test_the_shop(engine, client: TestClient, db: Session, gym_a) -> None:
    """Products, and a month of sales with their lines, members and payments
    (§20.1)."""
    from app.services import shop
    from tests.conftest import context_for

    sign_in(db, client, gym_a.owner)
    ctx = context_for(db, gym_a.owner)

    def add(n: int) -> None:
        product = shop.create_product(
            db, ctx, {"name": f"Bar {n}", "category": "snack", "price": 150_00,
                      "stock": 10}, None,
        )  # fmt: skip
        member = (
            make_member(db, gym_a, name=f"Buyer {n}", phone=f"98123600{n:02d}")
            if n % 2
            else None
        )
        shop.sell(
            db, ctx, lines=[(product.id, 1)], member_id=member.id if member else None,
            branch_id=None, discount=0, method="cash", transaction_ref=None, note=None,
        )  # fmt: skip
        db.commit()

    add(99)
    same_cost(engine, client, "/api/v1/products", add)

    def sales() -> list:
        return client.get("/api/v1/sales").json()["items"]

    one = queries(engine, sales)
    before = len(sales())
    for n in range(MORE):
        add(50 + n)
    assert len(sales()) == before + MORE
    assert queries(engine, sales) == one


def test_the_sales_book(engine, client: TestClient, db: Session, gym_a) -> None:
    """A month of tax invoices and credit notes (§20.4)."""
    from app.core.time import today_in_nepal

    sign_in(db, client, gym_a.owner)
    client.put(
        "/api/v1/gym/tax",
        json={
            "vat_registered": True,
            "pan": "301234567",
            "starts_on": today_in_nepal().isoformat(),
        },
    )

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Payer {n}", phone=f"98123700{n:02d}")
        _, payment = sell(db, gym_a, member, paid=1500_00)
        if n % 2:
            client.post(f"/api/v1/payments/{payment.id}/void", json={"reason": "Wrong"})

    def documents() -> list:
        book = client.get("/api/v1/tax-invoices").json()
        return book["invoices"] + book["returns"]

    add(99)
    one = queries(engine, documents)
    before = len(documents())
    for n in range(MORE):
        add(n)
    assert len(documents()) > before
    assert queries(engine, documents) == one


def test_gym_apps(engine, client: TestClient, db: Session, platform_admin) -> None:
    """Every gym's own app, in /admin (§20.3)."""
    from app.core.time import utcnow
    from app.models.branded_app import BrandedApp

    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)

    def add(n: int) -> None:
        gym = make_gym(db, slug=f"apps-{n}", phone=f"98123800{n:02d}")
        db.add(
            BrandedApp(
                gym_id=gym.gym.id,
                app_name=f"Gym {n}",
                color="#000000",
                android_package=f"np.gymbhai.g{n}",
                ios_bundle_id=f"np.gymbhai.g{n}",
                asked_at=utcnow(),
            )
        )
        db.commit()

    add(99)
    same_cost(engine, admin, "/api/v1/admin/apps", add)


def test_the_trend_on_reports(engine, client: TestClient, db: Session, gym_a) -> None:
    """Reports' charts: two years cost what two months do (§16.2, 7.9)."""
    sign_in(db, client, gym_a.owner)
    for n in range(3):
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98123900{n:02d}")
        sell(db, gym_a, member, paid=1500_00)

    def get(months: int):
        return lambda: client.get(f"/api/v1/reports/trend?months={months}").json()

    assert len(get(24)()["months"]) == 24
    assert queries(engine, get(2)) == queries(engine, get(24))


def test_extend_everyone(engine, client: TestClient, db: Session, gym_a) -> None:
    """Extend everyone (§5.6): the same statements for 2 memberships or 7."""
    sign_in(db, client, gym_a.owner)

    def add(n: int) -> None:
        member = make_member(db, gym_a, name=f"Member {n}", phone=f"98124000{n:02d}")
        sell(db, gym_a, member, paid=1500_00)

    def extend() -> None:
        response = client.post(
            "/api/v1/memberships/extend-all", json={"days": 1, "reason": "Power cut"}
        )
        assert response.status_code == 200, response.text

    add(98)
    add(99)
    few = queries(engine, extend)
    for n in range(MORE):
        add(n)
    assert queries(engine, extend) == few


def test_the_timetables_classes_are_made_in_one_go(engine, db: Session, gym_a) -> None:
    """The daily job makes four weeks of classes for every slot (§19.4) in a
    few statements, not one a class."""
    from app.models.classes import ClassSlot, ClassType
    from app.services import classes

    kind = ClassType(gym_id=gym_a.gym.id, name="Zumba", minutes=60, places=10)
    db.add(kind)
    db.commit()

    def add(n: int) -> None:
        db.add(
            ClassSlot(
                gym_id=gym_a.gym.id,
                branch_id=gym_a.branch.id,
                type_id=kind.id,
                weekday=n % 7,
                starts=f"{6 + n:02d}:00",
                minutes=60,
                places=10,
            )
        )
        db.commit()

    def make() -> None:
        classes.generate(db)
        db.commit()

    add(0)
    one = queries(engine, make)
    for n in range(1, MORE + 1):
        add(n)
    assert queries(engine, make) == one
