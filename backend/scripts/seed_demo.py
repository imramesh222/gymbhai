"""A demo gym that looks lived-in (PLAN.md §18.7): a year of members, money,
visits, expenses, enquiries and personal training, for showing GymBhai to a
gym or trying a screen with real-looking numbers.

    make seed-demo        (docker compose exec api python -m scripts.seed_demo)

Removes the gym `demo` if it is there and makes it again, through the same
services the desk uses, each action dated when it happened: the History tabs
read like a year at a gym, not one afternoon. The same people and habits on
every run (a fixed random seed); the dates follow today.

Refuses to run in production: everyone in it is made up, and its staff share
the password printed at the end. Members sign in to the member app with
MASTER_OTP, as on any development database.
"""

import datetime as dt
import random
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from unittest.mock import patch

from sqlalchemy import func, insert, select

import app.models  # noqa: F401  (registers every table)
from app.api.deps import staff_context
from app.api.tenancy import StaffContext
from app.core.calendar import days_in_bs_month, from_bs, plan_end_date, to_bs
from app.core.config import settings
from app.core.permissions import PRESETS
from app.core.security import hash_password
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import SessionLocal
from app.models.gym import Branch, Gym
from app.models.lead import (
    LEAD_CONTACTED,
    LEAD_JOINED,
    LEAD_LOST,
    LEAD_NEW,
    LEAD_TRIAL,
    Lead,
)
from app.models.member import Member
from app.models.member_app import (
    ALLOWED,
    DENIED_EXPIRED,
    METHOD_APP_QR,
    METHOD_CARD_QR,
    METHOD_MANUAL,
    CheckIn,
)
from app.models.membership import Membership
from app.models.messaging import Notice
from app.models.payment import GymPaymentMethod, Payment
from app.models.plan import Plan
from app.models.staff import StaffBranchAccess, StaffUser
from app.models.training import KIND_MONTHLY, KIND_SESSIONS, PtPackage, PtPlan
from app.schemas.auth import GymSignup
from app.services import (
    activity,
    freeze_requests,
    live,
    payment_requests,
    registration,
    training,
)
from app.services import expenses as expenses_service
from app.services import members as members_service
from app.services import memberships as ms
from scripts.seed_app_test import remove

SLUG = "demo"
PASSWORD = "demo-password-123"
OWNER = ("Rajesh Shrestha", "9800000200")
# (name, phone, starting point, branch: None for every branch)
STAFF = [
    ("Anita Gurung", "9800000201", "front_desk", None),
    ("Bikash Tamang", "9800000202", "trainer", "Baneshwor"),
    ("Sunita Rai", "9800000203", "trainer", "Koteshwor"),
]
MEMBERS = 170
SEED = 2083

FIRST_MEN = (
    "Aashish Amit Anish Bibek Bikram Bishal Dipesh Ganesh Hari Kiran Manoj Nabin "
    "Nischal Prakash Pratik Rajan Ramesh Roshan Sabin Sagar Sandeep Santosh Sujan "
    "Suman Sunil Suraj Sushant Tilak Ujjwal Yogesh"
).split()
FIRST_WOMEN = (
    "Aarati Anita Anjali Asmita Bina Binita Deepa Gita Kabita Kritika Laxmi Manisha "
    "Muna Nisha Pooja Prabha Pratiksha Rekha Rojina Sabina Samjhana Sarita Shristi "
    "Sita Srijana Sunita Sushma Uma Yamuna Puja"
).split()
LAST = (
    "Shrestha Maharjan Tamang Gurung Rai Limbu Magar Thapa Karki Khadka Adhikari "
    "Bhattarai Pokharel Poudel Sharma Joshi Bajracharya Shakya Lama Basnet KC Rana "
    "Thakuri Bista Dahal Ghimire Koirala Pradhan Singh Tuladhar"
).split()
METHODS = [("cash", 55), ("esewa", 20), ("khalti", 10), ("fonepay", 10), ("bank", 5)]
LOST_REASONS = ["Too expensive", "Too far from home", "Joined another gym", "Not now"]
SOURCES = [
    ("walk_in", 30),
    ("facebook", 20),
    ("instagram", 12),
    ("tiktok", 8),
    ("referral", 18),
    ("phone", 8),
    ("other", 4),
]

rng = random.Random(SEED)


def pick(weighted: list[tuple[str, int]]) -> str:
    return rng.choices([v for v, _ in weighted], [w for _, w in weighted])[0]


def at(day: dt.date, hour: int, minute: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=NEPAL)


def desk_time(day: dt.date, now: dt.datetime) -> dt.datetime:
    """When the desk did it that day: open hours, never later than now."""
    moment = at(day, rng.randint(6, 19), rng.randint(0, 59))
    return min(moment, now - dt.timedelta(minutes=rng.randint(2, 30)))


# Every module that dates what it records with utcnow().
TIMED = (activity, ms, training, expenses_service, members_service)


@contextmanager
def happened(moment: dt.datetime) -> Iterator[None]:
    """Everything recorded inside is dated `moment`: activity, cancellations,
    voids. Rows' own created_at is set by `dated()` after."""
    with ExitStack() as stack:
        for module in TIMED:
            if hasattr(module, "utcnow"):
                stack.enter_context(patch.object(module, "utcnow", lambda: moment))
        yield


def dated(db, moment: dt.datetime, *rows) -> None:
    """Written at once: a service that re-reads a row (a payment locks its
    membership) would otherwise put back the time it was made."""
    for row in rows:
        if row is not None:
            row.created_at = moment
            row.updated_at = moment
    db.flush()


@dataclass
class Period:
    """A membership as visits see it: its days, minus any freeze."""

    membership_id: object
    start: dt.date
    end: dt.date
    frozen: tuple[dt.date, dt.date] | None = None
    visit_limit: int | None = None
    morning_only: bool = False


@dataclass
class Person:
    member: Member
    visits_per_week: float
    morning: bool
    # Stopped coming this many days ago, though still paid up.
    drifting: int = 0
    periods: list[Period] = field(default_factory=list)


class Refs:
    """Transaction IDs: one use each in a gym, like the real thing."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def new(self, method: str) -> str | None:
        if method == "cash":
            return None
        prefix = {"esewa": "ESW", "khalti": "KHL", "fonepay": "FPY", "bank": "NIC"}
        while True:
            ref = f"{prefix[method]}{rng.randint(10_000_000, 99_999_999)}"
            if ref not in self.used:
                self.used.add(ref)
                return ref


def phones(count: int) -> Iterator[str]:
    seen: set[str] = set()
    while len(seen) < count:
        phone = f"98{rng.choice('14569')}{rng.randint(1_000_000, 9_999_999)}"
        if phone not in seen:
            seen.add(phone)
            yield phone


# --- the gym ----------------------------------------------------------------------


def make_gym(db):
    made = registration.register_gym(
        db,
        GymSignup(
            gym_name="Himalayan Fitness Club",
            slug=SLUG,
            plan_months="bs",
            date_display="both",
            owner_name=OWNER[0],
            owner_phone=OWNER[1],
            password=PASSWORD,
            accept_terms=True,
            branch_name="Baneshwor",
        ),
    )
    gym, owner = made.gym, made.owner
    gym.phone = "01-4782150"
    gym.address = "New Baneshwor, Kathmandu"
    gym.settings = {**gym.settings, "join_form": True}
    koteshwor = Branch(gym_id=gym.id, name="Koteshwor")
    db.add(koteshwor)
    db.flush()
    branches = {"Baneshwor": made.branch, "Koteshwor": koteshwor}

    staff = {}
    for name, phone, preset, branch in STAFF:
        person = StaffUser(
            gym_id=gym.id,
            name=name,
            phone=phone,
            password_hash=hash_password(PASSWORD),
            permissions=sorted(p.value for p in PRESETS[preset]),
        )
        db.add(person)
        db.flush()
        if branch:
            db.add(
                StaffBranchAccess(
                    staff_user_id=person.id, branch_id=branches[branch].id
                )
            )
        staff[name] = person
    db.flush()
    return gym, owner, branches, staff


def price_plans(db, gym: Gym) -> dict[str, Plan]:
    """The four seeded plans priced, an off-peak plan and a visit pack."""
    prices = {1: 2500_00, 3: 6500_00, 6: 12_000_00, 12: 21_000_00}
    plans = {}
    for plan in db.scalars(select(Plan).where(Plan.gym_id == gym.id)):
        plan.price = prices[plan.duration_months]
        plan.admission_fee = 1000_00
        plans[plan.name] = plan
    morning = Plan(
        gym_id=gym.id,
        name="Morning 1 month",
        duration_months=1,
        price=1800_00,
        admission_fee=1000_00,
        sort_order=5,
        access_hours=[{"days": list(range(7)), "from": "05:00", "to": "10:00"}],
    )
    pack = Plan(
        gym_id=gym.id,
        name="10 visits",
        duration_months=1,
        price=1500_00,
        admission_fee=0,
        sort_order=6,
        visit_limit=10,
    )
    db.add_all([morning, pack])
    db.add_all(
        GymPaymentMethod(
            gym_id=gym.id,
            kind=kind,
            label=label,
            account_name="Himalayan Fitness Club",
            account_number=number,
            sort_order=n,
        )
        for n, (kind, label, number) in enumerate(
            [
                ("esewa", "eSewa", "9800000200"),
                ("khalti", "Khalti", "9800000200"),
                ("bank", "NIC Asia Bank", "0123456789012"),
            ]
        )
    )
    db.flush()
    plans["Morning 1 month"] = morning
    plans["10 visits"] = pack
    return plans


# --- members, their memberships and money ------------------------------------------


PLAN_CHOICE = [
    ("1 month", 46),
    ("3 months", 26),
    ("6 months", 11),
    ("1 year", 7),
    ("Morning 1 month", 7),
    ("10 visits", 3),
]


def sell_history(
    db,
    gym: Gym,
    desk: StaffContext,
    owner: StaffContext,
    person: Person,
    plans: dict[str, Plan],
    refs: Refs,
    today: dt.date,
    now: dt.datetime,
) -> None:
    """Membership after membership from the day they joined, each paid in
    full or in part, some frozen, until they stop renewing or reach today."""
    member = person.member
    loyal = rng.choice([0.92, 0.85, 0.7, 0.5])
    favourite = pick(PLAN_CHOICE)
    start = member.joined_on
    sale_day = start
    first = True
    while sale_day <= today:
        name = favourite if rng.random() < 0.8 else pick(PLAN_CHOICE)
        plan = plans[name]
        end = plan_end_date(
            start,
            months=plan.duration_months,
            days=plan.duration_days,
            calendar=gym.config.plan_months,
        )
        price = plan.price or 0
        admission = plan.admission_fee if first else 0
        discount = rng.choice([0] * 8 + [250_00, 500_00]) if price > 2000_00 else 0
        total = price + admission - discount
        paid_now = total
        if rng.random() < 0.18:
            paid_now = max(
                500_00, round(total * rng.uniform(0.4, 0.8) / 100_00) * 100_00
            )
        method = pick(METHODS)
        moment = desk_time(sale_day, now)
        with happened(moment):
            membership, payment = ms.sell(
                db,
                desk,
                member,
                ms.SaleIn(
                    plan_id=plan.id,
                    branch_id=member.home_branch_id,
                    start_date=start,
                    end_date=end,
                    discount=discount,
                    payment=ms.PaymentIn(
                        amount=paid_now,
                        method=method,
                        transaction_ref=refs.new(method),
                        paid_at=moment,
                    ),
                ),
                gym.config,
            )
        dated(db, moment, membership, payment)

        # The rest of a part payment, usually within a few weeks.
        if paid_now < total:
            later = sale_day + dt.timedelta(days=rng.randint(3, 25))
            if later <= today and rng.random() < 0.85:
                method = pick(METHODS)
                when = desk_time(later, now)
                with happened(when):
                    rest = ms.record_payment(
                        db,
                        desk,
                        membership,
                        ms.PaymentIn(
                            amount=total - paid_now,
                            method=method,
                            transaction_ref=refs.new(method),
                            paid_at=when,
                        ),
                    )
                dated(db, when, rest)

        # Away for a while: a freeze moves the end date (§5.6).
        frozen = None
        if (plan.duration_months or 0) >= 3 and rng.random() < 0.15:
            begins = start + dt.timedelta(days=rng.randint(20, 60))
            if begins + dt.timedelta(days=30) < today:
                ends = begins + dt.timedelta(days=rng.randint(6, 20))
                with happened(desk_time(begins - dt.timedelta(days=1), now)):
                    ms.freeze(
                        db,
                        owner,
                        membership,
                        begins,
                        ends,
                        rng.choice(["Going home for Dashain", "Injury", "Travel"]),
                    )
                frozen = (begins, ends)

        person.periods.append(
            Period(
                membership_id=membership.id,
                start=start,
                end=membership.end_date,
                frozen=frozen,
                visit_limit=plan.visit_limit,
                morning_only=plan.access_hours is not None,
            )
        )
        first = False
        if rng.random() > loyal:
            return
        # Most renew a few days early; some come back after a gap.
        gap = 0 if rng.random() < 0.75 else rng.randint(3, 25)
        start = membership.end_date + dt.timedelta(days=1 + gap)
        sale_day = start - dt.timedelta(days=rng.randint(0, 5) if gap == 0 else 0)
        sale_day = max(sale_day, membership.start_date)


# --- visits ------------------------------------------------------------------------


def visits(
    person: Person,
    branches: dict[str, Branch],
    desk_staff: StaffUser,
    today: dt.date,
    now: dt.datetime,
) -> list[dict]:
    """Their check-ins: their habit, Saturdays quieter, none while frozen."""
    member = person.member
    other = next(b.id for b in branches.values() if b.id != member.home_branch_id)
    rows = []
    for period in person.periods:
        used = 0
        day = period.start
        while day <= min(period.end, today):
            if period.frozen and period.frozen[0] <= day <= period.frozen[1]:
                day += dt.timedelta(days=1)
                continue
            if person.drifting and (today - day).days < person.drifting:
                break
            chance = person.visits_per_week / 6.5 * (0.4 if day.weekday() == 5 else 1)
            if rng.random() < chance:
                if person.morning or period.morning_only:
                    hour, minute = rng.randint(5, 8), rng.randint(0, 59)
                else:
                    hour, minute = rng.randint(16, 20), rng.randint(0, 59)
                moment = at(day, hour, minute)
                if moment > now:
                    break
                method = rng.choices(
                    [METHOD_APP_QR, METHOD_CARD_QR, METHOD_MANUAL], [55, 30, 15]
                )[0]
                rows.append(
                    {
                        "gym_id": member.gym_id,
                        "branch_id": other
                        if rng.random() < 0.04
                        else member.home_branch_id,
                        "member_id": member.id,
                        "membership_id": period.membership_id,
                        "at": moment,
                        "method": method,
                        "result": ALLOWED,
                        "staff_user_id": desk_staff.id
                        if method == METHOD_MANUAL
                        else None,
                    }
                )
                used += 1
                if period.visit_limit and used >= period.visit_limit:
                    break
            day += dt.timedelta(days=1)

    # Came back after it ended: turned away at the door, once or twice.
    last = person.periods[-1] if person.periods else None
    if last and last.end < today and rng.random() < 0.3:
        tried = last.end + dt.timedelta(days=rng.randint(1, 6))
        if tried < today:
            rows.append(
                {
                    "gym_id": member.gym_id,
                    "branch_id": member.home_branch_id,
                    "member_id": member.id,
                    "membership_id": last.membership_id,
                    "at": at(tried, rng.randint(6, 19), rng.randint(0, 59)),
                    "method": METHOD_APP_QR,
                    "result": DENIED_EXPIRED,
                    "staff_user_id": None,
                }
            )
    return rows


# --- what the gym spent ------------------------------------------------------------

# (category, paid to, amount in rupees, day of the BS month (None: its last),
# branch or None). The gym keeps its books in BS months, as it counts plans.
MONTHLY = [
    ("rent", "Ram Bahadur Shrestha (landlord)", 75_000, 1, "Baneshwor"),
    ("rent", "Gita Maharjan (landlord)", 55_000, 2, "Koteshwor"),
    ("salaries", "Bikash Tamang (trainer)", 32_000, None, "Baneshwor"),
    ("salaries", "Sunita Rai (trainer)", 30_000, None, "Koteshwor"),
    ("salaries", "Anita Gurung (front desk)", 20_000, None, None),
    ("salaries", "Kamala BK (cleaning)", 12_000, None, None),
    ("internet", "WorldLink", 2_200, 10, None),
    ("water", "KUKL", 1_500, 12, None),
]


def bs_months(first: dt.date, last: dt.date) -> Iterator[tuple[dt.date, int]]:
    """Each BS month from the one `first` falls in: its first day, and length."""
    year, month, _ = to_bs(first)
    while (start := from_bs(year, month, 1)) <= last:
        yield start, days_in_bs_month(year, month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def spend(db, owner: StaffContext, branches: dict[str, Branch], today, now) -> int:
    first = today - dt.timedelta(days=365)
    rows = []
    for month, length in bs_months(first, today):
        for category, paid_to, rupees, day, branch in MONTHLY:
            offset = (day or length) - 1
            rows.append(
                (
                    month + dt.timedelta(days=offset),
                    category,
                    rupees,
                    paid_to,
                    branch,
                    "bank",
                )
            )
        # Electricity: more in the cold months, for the heaters and the lights.
        winter = (month + dt.timedelta(days=15)).month in (11, 12, 1, 2)
        for name in branches:
            rows.append(
                (
                    month + dt.timedelta(days=14),
                    "electricity",
                    rng.randint(9_000, 13_000) if winter else rng.randint(6_000, 9_000),
                    "NEA",
                    name,
                    "esewa",
                )
            )
        if rng.random() < 0.6:
            rows.append(
                (
                    month + dt.timedelta(days=rng.randint(4, 24)),
                    "marketing",
                    rng.choice([3_000, 5_000, 8_000]),
                    "Facebook ads",
                    None,
                    "bank",
                )
            )
        if rng.random() < 0.35:
            rows.append(
                (
                    month + dt.timedelta(days=rng.randint(4, 24)),
                    "repairs",
                    rng.randint(2_000, 12_000),
                    "Treadmill and cable repairs",
                    rng.choice(list(branches)),
                    "cash",
                )
            )
    rows.append(
        (
            today - dt.timedelta(days=200),
            "equipment",
            145_000,
            "Dumbbells 5–30 kg and racks",
            "Baneshwor",
            "bank",
        )
    )
    rows.append(
        (
            today - dt.timedelta(days=75),
            "equipment",
            92_000,
            "Two spin bikes",
            "Koteshwor",
            "bank",
        )
    )
    made = 0
    for spent_on, category, rupees, paid_to, branch, method in rows:
        if spent_on < first or spent_on > today:
            continue
        when = min(at(spent_on, 11, rng.randint(0, 59)), now)
        with happened(when):
            expense = expenses_service.create(
                db,
                owner,
                {
                    "branch_id": branches[branch].id if branch else None,
                    "category": category,
                    "amount": rupees * 100,
                    "spent_on": spent_on,
                    "method": method,
                    "paid_to": paid_to,
                    "note": None,
                },
            )
        dated(db, when, expense)
        made += 1
    return made


# --- enquiries ---------------------------------------------------------------------


def enquiries(db, gym, branches, plans, people, staff, today) -> int:
    """People who asked: most recent ones still open, older ones joined or not."""
    firsts = rng.sample(FIRST_MEN + FIRST_WOMEN, 40)
    names = list(zip(firsts, rng.choices(LAST, k=40), strict=True))
    joined = [p for p in people if p.member.referred_by_id is None][:20]
    made = 0
    for n, (first, last) in enumerate(names[:28]):
        age = rng.randint(0, 300)
        created = today - dt.timedelta(days=age)
        status = (
            rng.choice([LEAD_NEW, LEAD_CONTACTED, LEAD_TRIAL])
            if age < 30
            else LEAD_LOST
        )
        lead = Lead(
            gym_id=gym.id,
            branch_id=rng.choice(list(branches.values())).id,
            name=f"{first} {last}",
            phone=f"97{rng.randint(10_000_000, 99_999_999)}",
            source=pick(SOURCES),
            plan_id=rng.choice(list(plans.values())).id,
            status=status,
            follow_up_on=today + dt.timedelta(days=rng.randint(-3, 5))
            if status != LEAD_LOST
            else None,
            trial_on=created + dt.timedelta(days=2) if status == LEAD_TRIAL else None,
            lost_reason=rng.choice(LOST_REASONS) if status == LEAD_LOST else None,
            assigned_to=staff["Anita Gurung"].id,
            created_at=at(created, 10, n % 60),
        )
        db.add(lead)
        made += 1
    # Those who joined: their enquiry, linked to the member it became.
    for person in joined:
        member = person.member
        db.add(
            Lead(
                gym_id=gym.id,
                branch_id=member.home_branch_id,
                name=member.name,
                phone=member.phone,
                source=pick(SOURCES),
                status=LEAD_JOINED,
                member_id=member.id,
                assigned_to=staff["Anita Gurung"].id,
                created_at=at(member.joined_on - dt.timedelta(days=3), 17, 5),
            )
        )
        made += 1
    db.flush()
    return made


# --- personal training -------------------------------------------------------------


def personal_training(db, gym, desk, trainers, people, refs, today, now) -> int:
    pack = PtPlan(
        gym_id=gym.id,
        name="12 sessions",
        kind=KIND_SESSIONS,
        sessions=12,
        duration_months=2,
        price=12_000_00,
    )
    monthly = PtPlan(
        gym_id=gym.id,
        name="Monthly PT",
        kind=KIND_MONTHLY,
        duration_months=1,
        price=8_000_00,
    )
    db.add_all([pack, monthly])
    db.flush()
    candidates = [p for p in people if p.periods and not p.member.is_archived]
    clients = rng.sample(candidates, min(16, len(candidates)))
    made = 0
    for n, person in enumerate(clients):
        member = person.member
        trainer_ctx, trainer = trainers[n % len(trainers)]
        plan = pack if n % 3 else monthly
        # While they were a member: PT on top of a membership.
        period = rng.choice([p for p in person.periods if p.start <= today])
        start = min(period.start + dt.timedelta(days=rng.randint(0, 15)), today)
        moment = desk_time(start, now)
        paid = plan.price if rng.random() < 0.7 else plan.price // 2
        method = pick(METHODS)
        with happened(moment):
            package, payment = training.sell(
                db,
                desk,
                member,
                training.SaleIn(
                    plan_id=plan.id,
                    trainer_id=trainer.id,
                    branch_id=member.home_branch_id,
                    start_date=start,
                    payment=ms.PaymentIn(
                        amount=paid,
                        method=method,
                        transaction_ref=refs.new(method),
                        paid_at=moment,
                    ),
                ),
                gym.config,
            )
        dated(db, moment, package, payment)
        # Twice a week or so, through to today.
        day, used = start, 0
        while day <= min(package.end_date, today):
            if day.weekday() in (0, 3) or rng.random() < 0.1:
                if package.sessions is not None and used >= package.sessions:
                    break
                when = at(day, 7 if person.morning else 18, rng.randint(0, 50))
                if when > now:
                    break
                with happened(when):
                    session = training.record_session(
                        db,
                        trainer_ctx,
                        package,
                        day,
                        rng.choice([None, "Legs and core", "Upper body", "Cardio"]),
                    )
                dated(db, when, session)
                used += 1
            day += dt.timedelta(days=1)
        made += 1
    return made


# --- the rest of a day at the desk -------------------------------------------------


def waiting(
    db, gym: Gym, people: list[Person], plans, refs: Refs, today: dt.date
) -> None:
    """What's waiting for someone now: two payments sent from the app and a
    freeze request, as on any morning."""
    ending = [
        p
        for p in people
        if p.periods and today <= p.periods[-1].end <= today + dt.timedelta(days=6)
    ]
    esewa = db.scalar(
        select(GymPaymentMethod).where(
            GymPaymentMethod.gym_id == gym.id, GymPaymentMethod.kind == "esewa"
        )
    )
    for person in ending[:2]:
        payment_requests.create(
            db,
            person.member,
            plan_id=plans["1 month"].id,
            payment_method_id=esewa.id if esewa else None,
            amount=plans["1 month"].price or 0,
            transaction_ref=refs.new("esewa"),
        )
    long_ones = [
        p
        for p in people
        if p.periods and p.periods[-1].end > today + dt.timedelta(days=40)
    ]
    if long_ones:
        freeze_requests.create(
            db,
            long_ones[0].member,
            from_date=today + dt.timedelta(days=4),
            to_date=today + dt.timedelta(days=13),
            reason="Going home for Tihar",
        )


def notices(db, gym: Gym, owner: StaffUser, now: dt.datetime) -> None:
    for days, title, body in [
        (
            70,
            "New spin bikes in Koteshwor",
            "Two new spin bikes are in. Ask at the desk for the evening class.",
        ),
        (
            21,
            "Closed for Ghatasthapana",
            "Both branches close for the day. Happy Dashain from all of us!",
        ),
        (
            3,
            "Morning batch from 5:30",
            "From Sunday the morning batch starts at 5:30, not 6.",
        ),
    ]:
        db.add(
            Notice(
                gym_id=gym.id,
                title=title,
                body=body,
                published_at=now - dt.timedelta(days=days),
                created_by=owner.id,
            )
        )


# --- making it ---------------------------------------------------------------------


def build(db, *, members: int = MEMBERS, say=print) -> tuple[dict[str, int], str]:
    """Make the demo gym in `db`, uncommitted: what it holds, and one member's
    phone for the member app. The same gym every time it's called."""
    rng.seed(SEED)
    now = utcnow().astimezone(NEPAL)
    today = today_in_nepal()
    year_ago = today - dt.timedelta(days=365)
    # A new gym nobody is watching: no live events for it.
    with patch.object(live, "publish", lambda *a, **k: None):
        remove(db, SLUG)
        gym, owner_row, branches, staff = make_gym(db)
        plans = price_plans(db, gym)
        # On GymBhai since before its first member: Reports' trends start
        # from the month a gym joined.
        dated(
            db,
            at(year_ago - dt.timedelta(days=3), 9, 0),
            gym,
            owner_row,
            *branches.values(),
            *staff.values(),
            *plans.values(),
        )
        owner = staff_context(owner_row, db)
        desk_row = staff["Anita Gurung"]
        desk = staff_context(desk_row, db)
        trainers = [
            (staff_context(staff[name], db), staff[name])
            for name in ("Bikash Tamang", "Sunita Rai")
        ]
        refs = Refs()

        # Members joined over the year, more of them lately.
        numbers = phones(members)
        people: list[Person] = []
        joined_days = sorted(
            year_ago + dt.timedelta(days=int(365 * rng.random() ** 0.8))
            for _ in range(members)
        )
        for n, joined in enumerate(joined_days):
            woman = rng.random() < 0.42
            first = rng.choice(FIRST_WOMEN if woman else FIRST_MEN)
            branch = branches["Baneshwor" if rng.random() < 0.65 else "Koteshwor"]
            referrer = (
                rng.choice(people).member.id if people and rng.random() < 0.15 else None
            )
            moment = desk_time(joined, now)
            with happened(moment):
                member = members_service.create(
                    db,
                    desk,
                    {
                        "name": f"{first} {rng.choice(LAST)}",
                        "phone": next(numbers),
                        "gender": "female" if woman else "male",
                        "home_branch_id": branch.id,
                        "joined_on": joined,
                        "referred_by_id": referrer,
                        "date_of_birth": dt.date(
                            rng.randint(1975, 2007),
                            rng.randint(1, 12),
                            rng.randint(1, 28),
                        ),
                    },
                    gym.config,
                )
            dated(db, moment, member)
            person = Person(
                member=member,
                visits_per_week=min(6.0, max(1.0, rng.gauss(3.6, 1.2))),
                morning=rng.random() < 0.6,
                drifting=rng.randint(16, 40) if rng.random() < 0.08 else 0,
            )
            sell_history(db, gym, desk, owner, person, plans, refs, today, now)
            people.append(person)
            if n % 25 == 24:
                say(f"  {n + 1} members…")

        # Left long ago: archived, as a desk tidies its list.
        gone = [
            p
            for p in people
            if p.periods and p.periods[-1].end < today - dt.timedelta(days=120)
        ]
        for person in gone[:4]:
            when = desk_time(person.periods[-1].end + dt.timedelta(days=60), now)
            with happened(when):
                members_service.update(
                    db,
                    owner,
                    person.member,
                    {"is_archived": True},
                    action="member.archived",
                    reason="Moved away",
                )

        say("  visits…")
        rows = [
            row
            for person in people
            for row in visits(person, branches, desk_row, today, now)
        ]
        for chunk in range(0, len(rows), 5000):
            db.execute(insert(CheckIn), rows[chunk : chunk + 5000])

        spent = spend(db, owner, branches, today, now)
        asked = enquiries(db, gym, branches, plans, people, staff, today)
        personal_training(db, gym, desk, trainers, people, refs, today, now)
        notices(db, gym, owner_row, now)
        waiting(db, gym, people, plans, refs, today)
        db.flush()

    def count(model) -> int:
        return db.scalar(select(func.count()).where(model.gym_id == gym.id)) or 0

    counts = {
        "members": count(Member),
        "memberships": count(Membership),
        "payments": count(Payment),
        "visits": len(rows),
        "expenses": spent,
        "enquiries": asked,
        "personal training": count(PtPackage),
    }
    return counts, people[-1].member.phone


def main() -> int:
    if settings.environment == "production":
        print("Not in production: the demo gym is made up, with a shared password.")
        return 1
    with SessionLocal() as db:
        counts, member_phone = build(db, say=lambda text: print(text, flush=True))
        db.commit()

    print(f"\nThe demo gym is ready: /{SLUG}, Himalayan Fitness Club.")
    print("  " + ", ".join(f"{count} {name}" for name, count in counts.items()))
    print(f"\nStaff sign in at /staff/login, password {PASSWORD}:")
    print(f"  {OWNER[0]:<16} {OWNER[1]}  owner")
    for name, phone, preset, branch in STAFF:
        where = f", {branch}" if branch else ""
        print(f"  {name:<16} {phone}  {preset.replace('_', ' ')}{where}")
    print(f"\nA member, for the app at /{SLUG}: {member_phone} (MASTER_OTP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
