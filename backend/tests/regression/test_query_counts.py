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
