"""Shared fixtures.

Integration and regression tests run against a real PostgreSQL: a separate
`<db>_test` database, created if missing, with every test inside a transaction
that is rolled back afterwards. Without a reachable database those tests are
skipped and the unit tier still runs.
"""

import os

# Settings are read at import time, so the environment is fixed first. These
# are assignments, not setdefault: a developer's .env must not decide what the
# suite talks to or how it signs tokens.
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-only-signing-key-that-is-long-enough"
os.environ["TRUSTED_PROXY_COUNT"] = "0"

from collections.abc import Callable, Generator
from dataclasses import dataclass
from functools import cache

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers every table)
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.gym import Branch, Gym
from app.models.staff import StaffBranchAccess, StaffUser
from app.schemas.auth import GymSignup
from app.services import registration, sessions

TEST_PASSWORD = "correct-horse-battery"


@cache
def shared_password_hash() -> str:
    """bcrypt is slow on purpose; hash the shared test password once."""
    return hash_password(TEST_PASSWORD)


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


TEST_DATABASE_URL = _test_database_url()


@pytest.fixture(scope="session")
def engine() -> Generator[sa.Engine]:
    parsed = make_url(TEST_DATABASE_URL)
    try:
        admin = sa.create_engine(
            parsed.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": 5},
        )
        with admin.connect() as connection:
            exists = connection.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": parsed.database},
            ).first()
            if not exists:
                connection.execute(sa.text(f'CREATE DATABASE "{parsed.database}"'))
        admin.dispose()
    except sa.exc.OperationalError as exc:
        pytest.skip(f"No PostgreSQL at {parsed.render_as_string()}: {exc}")

    engine = sa.create_engine(TEST_DATABASE_URL, poolclass=sa.pool.NullPool)
    # A clean slate, in case an earlier run was killed before teardown.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: sa.Engine) -> Generator[Session]:
    """A session whose work is all rolled back after the test.

    "create_savepoint" turns the application's own commit() and rollback()
    into savepoint operations, so routes behave as in production while the
    outer transaction still undoes everything.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    """Signed out. Sign in with `sign_in(db, client, staff)` or the login route."""

    def override_get_db() -> Generator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@dataclass
class GymFixture:
    gym: Gym
    branch: Branch
    owner: StaffUser


def make_gym(
    db: Session,
    *,
    slug: str,
    phone: str,
    email: str | None = None,
    plan_months: str = "bs",
    date_display: str = "both",
) -> GymFixture:
    """A gym made the way sign-up makes one."""
    result = registration.register_gym(
        db,
        GymSignup(
            gym_name=f"Gym {slug}",
            slug=slug,
            plan_months=plan_months,
            date_display=date_display,
            owner_name=f"Owner of {slug}",
            owner_phone=phone,
            owner_email=email,
            password=TEST_PASSWORD,
        ),
    )
    db.commit()
    return GymFixture(result.gym, result.branch, result.owner)


@pytest.fixture
def gym_a(db: Session) -> GymFixture:
    return make_gym(db, slug="fitness-zone", phone="9841000001", email="a@example.com")


@pytest.fixture
def gym_b(db: Session) -> GymFixture:
    """A second gym, for proving that nothing leaks between gyms."""
    return make_gym(db, slug="iron-house", phone="9801000002", email="b@example.com")


@pytest.fixture
def make_staff(db: Session) -> Callable[..., StaffUser]:
    counter = iter(range(100, 1000))

    def factory(
        gym: Gym,
        *,
        permissions: list[str] | None = None,
        branches: list[Branch] | None = None,
        is_active: bool = True,
    ) -> StaffUser:
        n = next(counter)
        staff = StaffUser(
            gym_id=gym.id,
            name=f"Staff {n}",
            phone=f"98420{n:05d}",
            password_hash=shared_password_hash(),
            permissions=permissions or [],
            is_active=is_active,
        )
        db.add(staff)
        db.flush()
        for branch in branches or []:
            db.add(StaffBranchAccess(staff_user_id=staff.id, branch_id=branch.id))
        db.commit()
        return staff

    return factory


def sign_in(db: Session, client: TestClient, staff: StaffUser) -> str:
    """Open a real session for `staff` and send its token on every request."""
    issued = sessions.start(db, staff, None)
    db.commit()
    client.headers["Authorization"] = f"Bearer {issued.access_token}"
    return issued.access_token


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]):
    """Mark each test by its directory, so `-m unit` and friends work."""
    for item in items:
        for tier in ("unit", "integration", "regression"):
            if tier in item.path.parts:
                item.add_marker(getattr(pytest.mark, tier))
                break


# --- members and money --------------------------------------------------------


def context_for(db: Session, staff: StaffUser):
    """The StaffContext a request by `staff` would get, for calling services."""
    from app.api.deps import staff_context

    return staff_context(staff, db)


def priced_plan(db: Session, gym: Gym, *, months: int = 1, price: int = 1500_00):
    """One of the seeded plans, with a price set (sign-up leaves them blank)."""
    from sqlalchemy import select

    from app.models.plan import Plan

    plan = db.scalars(
        select(Plan).where(Plan.gym_id == gym.id, Plan.duration_months == months)
    ).one()
    plan.price = price
    db.commit()
    return plan


def make_member(
    db: Session, fixture: "GymFixture", *, name: str = "Sita Rai", phone="9812345678"
):
    from app.services import members as members_service

    ctx = context_for(db, fixture.owner)
    member = members_service.create(
        db, ctx, {"name": name, "phone": phone}, fixture.gym.config
    )
    db.commit()
    return member


def sell(db: Session, fixture: "GymFixture", member, *, paid: int = 0, **sale):
    """Sell the 1-month plan (Rs 1,500 unless given) to `member`."""
    from app.services import memberships as ms

    ctx = context_for(db, fixture.owner)
    plan = sale.pop("plan", None) or priced_plan(db, fixture.gym)
    payment = ms.PaymentIn(amount=paid, method="cash") if paid else None
    membership, payment_row = ms.sell(
        db,
        ctx,
        member,
        ms.SaleIn(plan_id=plan.id, payment=payment, **sale),
        fixture.gym.config,
    )
    db.commit()
    return membership, payment_row


@pytest.fixture
def platform_admin(db: Session) -> StaffUser:
    admin = StaffUser(
        name="GymBhai admin",
        email="admin@gymbhai.com",
        password_hash=shared_password_hash(),
        is_platform_admin=True,
    )
    db.add(admin)
    db.commit()
    return admin


def lapse(db: Session, gym: Gym, days_ago: int = 30) -> None:
    """End the gym's subscription `days_ago` days ago (past the 7-day grace)."""
    import datetime as dt

    from app.core.time import today_in_nepal
    from app.services import subscription

    row = subscription.latest(db, gym.id)
    row.starts_on = today_in_nepal() - dt.timedelta(days=days_ago + 14)
    row.ends_on = today_in_nepal() - dt.timedelta(days=days_ago)
    db.commit()
