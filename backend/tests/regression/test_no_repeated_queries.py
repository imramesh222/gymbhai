"""No request runs the same SQL over and over (no N+1), anywhere.

The query-count tests check one list each; these sweep every GET endpoint,
the daily jobs and the actions that touch many members at once, on the demo
gym (a year of members, money, visits and classes), and fail when one of them
runs any single statement more than MAX_REPEATS times: the shape of a query
made once per row. The worker's own jobs are one SMS or push each, so they
aren't swept.
"""

import re
from collections import Counter
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.classes import ClassBooking, GymClass
from app.models.gym import Branch, Gym
from app.models.lead import Lead
from app.models.member import Member
from app.models.member_app import CheckIn
from app.models.membership import Membership, MembershipGroup
from app.models.payment import Payment
from app.models.shop import Product
from app.models.staff import StaffUser
from app.services import member_auth
from scripts import seed_demo
from tests.conftest import sign_in
from tests.routes import all_routes

MAX_REPEATS = 3

# Streams, files by signed link, readers and kiosks (device tokens), Meta's
# webhook: none of them lists anything from the database by the row.
SKIP = (
    "/health",
    "/iclock",
    "/api/v1/kiosk",
    "/api/v1/live",
    "/api/v1/m/live",
    "/api/v1/files",
    "/api/v1/receipts",
    "/api/v1/pay/",
    "/api/v1/whatsapp",
    "/api/v1/m/online-payments",
    "/api/v1/m/{slug}/logo",
    "/api/v1/admin/apps/{app_id}",
)
EXPORTS = (
    "members",
    "memberships",
    "payments",
    "expenses",
    "sales",
    "sales-book",
    "sales-returns",
    "check-ins",
)


def repeats(engine: sa.Engine, call: Callable[[], object]) -> tuple[int, str]:
    """How often the most repeated statement ran during `call`, and which."""
    seen: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            seen.append(re.sub(r"\s+", " ", statement).strip())

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        call()
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)
    if not seen:
        return 0, ""
    statement, times = Counter(seen).most_common(1)[0]
    return times, statement[:240]


def demo_gym(db: Session) -> tuple[Gym, StaffUser]:
    seed_demo.build(db, members=30, say=lambda _: None)
    db.commit()
    gym = db.scalar(select(Gym).where(Gym.slug == "demo"))
    owner = db.scalar(
        select(StaffUser).where(StaffUser.gym_id == gym.id, StaffUser.is_owner)
    )
    return gym, owner


def most(db: Session, column, *where) -> object:
    """The value of `column` with the most rows: the busiest member, class..."""
    return db.execute(
        select(column, func.count()).where(*where).group_by(column)
        .order_by(func.count().desc()).limit(1)
    ).first()[0]  # fmt: skip


def test_no_get_endpoint_repeats_a_query(
    engine: sa.Engine, client: TestClient, db: Session, platform_admin
) -> None:
    gym, owner = demo_gym(db)
    member = db.get(
        Member,
        most(
            db,
            Payment.member_id,
            Payment.gym_id == gym.id,
            Payment.member_id.is_not(None),
        ),
    )
    busiest_class = most(
        db,
        GymClass.id,
        GymClass.gym_id == gym.id,
        ClassBooking.class_id == GymClass.id,
    )
    group = db.scalar(select(MembershipGroup).where(MembershipGroup.gym_id == gym.id))
    lead = db.scalar(select(Lead).where(Lead.gym_id == gym.id).limit(1))
    fill = {
        "branch_id": db.scalar(
            select(Branch.id).where(Branch.gym_id == gym.id).limit(1)
        ),
        "member_id": member.id,
        "membership_id": db.scalar(
            select(Membership.id).where(Membership.member_id == member.id).limit(1)
        ),
        "payment_id": db.scalar(
            select(Payment.id).where(Payment.member_id == member.id).limit(1)
        ),
        "product_id": db.scalar(
            select(Product.id).where(Product.gym_id == gym.id).limit(1)
        ),
        "class_id": busiest_class,
        "group_id": group.id if group else None,
        "lead_id": lead.id if lead else None,
        "gym_id": gym.id,
        "slug": "demo",
    }

    # The member who comes most, for the member app.
    visitor = db.get(Member, most(db, CheckIn.member_id, CheckIn.gym_id == gym.id))
    issued = member_auth.start_session(db, visitor, None)
    db.commit()
    app = TestClient(client.app)
    app.headers["Authorization"] = f"Bearer {issued.access_token}"
    admin = TestClient(client.app)
    sign_in(db, admin, platform_admin)
    sign_in(db, client, owner)

    urls: list[tuple[TestClient, str]] = []
    for method, path, _ in all_routes():
        if method != "GET" or path.startswith(SKIP):
            continue
        if path == "/api/v1/export/{kind}.xlsx":
            urls += [(client, f"/api/v1/export/{kind}.xlsx") for kind in EXPORTS]
            continue
        names = re.findall(r"{(\w+)}", path)
        if any(fill.get(name) is None for name in names):
            continue
        url = path
        for name in names:
            url = url.replace("{" + name + "}", str(fill[name]))
        if path.startswith("/api/v1/admin"):
            urls.append((admin, url))
        elif path.startswith("/api/v1/m/"):
            urls.append((app, url))
        else:
            urls.append((client, url))
    # The lists again with their filters.
    for status in ("active", "ending", "expired", "owing", "frozen", "archived"):
        urls.append((client, f"/api/v1/members?filter={status}&limit=100"))
    for tab in ("ending", "lapsed", "owing", "not-visiting"):
        urls.append((client, f"/api/v1/lists/follow-up?tab={tab}"))
    urls += [
        (client, "/api/v1/check-ins?days=30"),
        (client, "/api/v1/payments?limit=500"),
    ]

    bad, broken = [], []
    for who, url in urls:
        codes: list[int] = []

        def get(who: TestClient = who, url: str = url, codes: list = codes) -> None:
            codes.append(who.get(url).status_code)

        times, statement = repeats(engine, get)
        if codes[0] >= 500:
            broken.append(f"{url}: {codes[0]}")
        if times > MAX_REPEATS:
            bad.append(f"{url}: {times}x {statement}")
    assert len(urls) > 100
    assert not broken, broken
    assert not bad, "\n".join(bad)


def test_no_job_or_bulk_action_repeats_a_query(
    engine: sa.Engine, client: TestClient, db: Session
) -> None:
    from app.services import classes, owner_messages, reminders

    gym, owner = demo_gym(db)
    sign_in(db, client, owner)
    ids = [
        str(m) for m in db.scalars(select(Member.id).where(Member.gym_id == gym.id))
    ][:60]

    def done(call: Callable[[], object]) -> Callable[[], None]:
        def run() -> None:
            call()
            db.commit()

        return run

    actions = {
        "daily reminders": lambda: reminders.handle_daily(db, {}),
        "the timetable's classes": lambda: classes.handle_generate(db, {}),
        "owners' daily summaries": lambda: owner_messages.daily_summaries(db),
        "subscription reminders": lambda: owner_messages.subscription_reminders(db),
        "setup nudges": lambda: owner_messages.setup_nudges(db),
        "Extend everyone": lambda: client.post(
            "/api/v1/memberships/extend-all", json={"days": 3, "reason": "Dashain"}
        ),
        "a notice with SMS": lambda: client.post(
            "/api/v1/notices",
            json={"title": "Closed", "body": "Closed Saturday.", "send_sms": True},
        ),
        "SMS to members picked": lambda: client.post(
            "/api/v1/members/sms", json={"member_ids": ids, "body": "Hello"}
        ),
    }
    bad = []
    for label, call in actions.items():
        times, statement = repeats(engine, done(call))
        if times > MAX_REPEATS:
            bad.append(f"{label}: {times}x {statement}")
    assert not bad, "\n".join(bad)
