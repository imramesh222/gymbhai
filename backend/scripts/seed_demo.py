"""A demo gym that looks lived-in (PLAN.md §18.7): a year of members, money,
visits, expenses, enquiries and personal training; couples and a family on
one plan, classes with their bookings and who came, progress checks, and the
messages sent (SMS and WhatsApp), for showing GymBhai to a gym or trying a
screen with real-looking numbers.

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
from app.core.calendar import (
    days_in_bs_month,
    format_date,
    from_bs,
    plan_end_date,
    to_bs,
)
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import PRESETS
from app.core.security import hash_password
from app.core.time import NEPAL, today_in_nepal, utcnow
from app.db.session import SessionLocal
from app.models.classes import CLASSES_CHOSEN, CLASSES_NONE, ClassSlot, ClassType
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
from app.models.messaging import (
    CHANNEL_SMS,
    CHANNEL_WHATSAPP,
    SMS_REMINDER,
    SMS_SENT,
    Notice,
    SmsCreditLedger,
    SmsMessage,
)
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
from app.services import classes as classes_service
from app.services import expenses as expenses_service
from app.services import members as members_service
from app.services import memberships as ms
from app.services import progress as progress_service
from app.services import shop as shop_service
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
TIMED = (
    activity,
    ms,
    training,
    expenses_service,
    members_service,
    classes_service,
    progress_service,
    shop_service,
)


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
    # WhatsApp on (§19.3): it works with the console provider on a laptop.
    gym.settings = {
        **gym.settings,
        # Chosen on Plans, before the first sale (§5.1).
        "plan_months": "bs",
        "join_form": True,
        "whatsapp": True,
    }
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


# Class types (§19.4): (name, minutes, places, colour).
CLASS_TYPES = [
    ("Zumba", 60, 20, "pink"),
    ("Yoga", 60, 15, "green"),
    ("Spin", 45, 10, "orange"),
    ("HIIT", 45, 16, "blue"),
]
# The weekly timetable: (type, branch, weekdays (0 is Monday), start, instructor).
TIMETABLE = [
    ("Zumba", "Baneshwor", (0, 2, 4), "07:00", "Bikash Tamang"),
    ("Zumba", "Baneshwor", (1, 3), "18:00", "Bikash Tamang"),
    ("Yoga", "Baneshwor", (6, 1, 3), "06:00", "Bikash Tamang"),
    ("Spin", "Koteshwor", (0, 2, 4), "18:30", "Sunita Rai"),
    ("HIIT", "Koteshwor", (6, 1, 3), "07:00", "Sunita Rai"),
    ("Zumba", "Koteshwor", (5,), "08:00", "Sunita Rai"),
]


def class_types(db, gym: Gym) -> dict[str, ClassType]:
    kinds = {}
    for n, (name, minutes, places, color) in enumerate(CLASS_TYPES):
        kinds[name] = ClassType(
            gym_id=gym.id,
            name=name,
            minutes=minutes,
            places=places,
            color=color,
            sort_order=n,
        )
    db.add_all(kinds.values())
    db.flush()
    return kinds


def price_plans(db, gym: Gym, kinds: dict[str, ClassType]) -> dict[str, Plan]:
    """The four seeded plans priced, an off-peak plan and a visit pack; a
    couple's and a family's plan (§19.1), and a Zumba-only plan (§19.4)."""
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
    # The visit pack is for the gym floor: no classes.
    pack.classes = CLASSES_NONE
    couple = Plan(
        gym_id=gym.id,
        name="Couple 1 year",
        duration_months=12,
        price=38_000_00,
        admission_fee=1000_00,
        sort_order=7,
        seats=2,
    )
    family = Plan(
        gym_id=gym.id,
        name="Family 3 months",
        duration_months=3,
        price=16_000_00,
        admission_fee=500_00,
        sort_order=8,
        seats=4,
    )
    zumba = Plan(
        gym_id=gym.id,
        name="Zumba 1 month",
        duration_months=1,
        price=2000_00,
        admission_fee=0,
        sort_order=9,
        classes=CLASSES_CHOSEN,
        class_type_ids=[str(kinds["Zumba"].id)],
    )
    db.add_all([morning, pack, couple, family, zumba])
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
    plans["Couple 1 year"] = couple
    plans["Family 3 months"] = family
    plans["Zumba 1 month"] = zumba
    return plans


# --- members, their memberships and money ------------------------------------------


PLAN_CHOICE = [
    ("1 month", 46),
    ("3 months", 26),
    ("6 months", 11),
    ("1 year", 7),
    ("Morning 1 month", 7),
    ("10 visits", 3),
    ("Zumba 1 month", 3),
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


# --- couples and a family (§19.1) ---------------------------------------------------

# (plan, the payer's first name, the others' first names, a last name,
# joined this many days ago, renewed once since)
GROUPS = [
    ("Couple 1 year", "Sagar", ["Pooja"], "Adhikari", 300, False),
    ("Couple 1 year", "Nabin", ["Rekha"], "Gurung", 120, False),
    ("Family 3 months", "Prakash", ["Laxmi", "Aayush"], "Thapa", 150, True),
    ("Family 3 months", "Suman", ["Sushma"], "Basnet", 40, False),
]
FAMILY_PEOPLE = sum(1 + len(others) for _, _, others, _, _, _ in GROUPS)


def families(
    db,
    gym: Gym,
    desk: StaffContext,
    plans: dict[str, Plan],
    branches: dict[str, Branch],
    numbers: Iterator[str],
    refs: Refs,
    today: dt.date,
    now: dt.datetime,
) -> list[Person]:
    """One sale for several people, the money on the payer's membership; a
    child on a parent's phone; a family that renewed together."""
    people = []
    branch = branches["Baneshwor"]
    for plan_name, payer_first, others, last, ago, renewed in GROUPS:
        plan = plans[plan_name]
        joined = today - dt.timedelta(days=ago)
        moment = desk_time(joined, now)
        phone = next(numbers)
        made = []
        for n, first in enumerate([payer_first, *others]):
            child = first == "Aayush"
            with happened(moment):
                member = members_service.create(
                    db,
                    desk,
                    {
                        "name": f"{first} {last}",
                        # A child on a parent's number (§5.5).
                        "phone": phone
                        if child
                        else (phone if n == 0 else next(numbers)),
                        "gender": "female" if first in FIRST_WOMEN else "male",
                        "home_branch_id": branch.id,
                        "joined_on": joined,
                        "whatsapp_agreed": n == 0,
                    },
                    gym.config,
                )
            dated(db, moment, member)
            made.append(member)
        payer, rest = made[0], made[1:]
        start, sale_day = joined, joined
        periods: dict[object, list[Period]] = {m.id: [] for m in made}
        for _ in range(2 if renewed else 1):
            end = plan_end_date(
                start,
                months=plan.duration_months,
                days=plan.duration_days,
                calendar=gym.config.plan_months,
            )
            moment = desk_time(sale_day, now)
            with happened(moment):
                membership, _ = ms.sell(
                    db,
                    desk,
                    payer,
                    ms.SaleIn(
                        plan_id=plan.id,
                        branch_id=branch.id,
                        start_date=start,
                        end_date=end,
                        with_member_ids=[m.id for m in rest],
                    ),
                    gym.config,
                )
                method = pick(METHODS)
                payment = ms.record_payment(
                    db,
                    desk,
                    membership,
                    ms.PaymentIn(
                        amount=ms.amount_due(membership),
                        method=method,
                        transaction_ref=refs.new(method),
                        paid_at=moment,
                    ),
                )
            group = ms.group_memberships(db, membership.group_id)
            dated(db, moment, payment, *group)
            for row in group:
                periods[row.member_id].append(
                    Period(membership_id=row.id, start=row.start_date, end=row.end_date)
                )
            start = membership.end_date + dt.timedelta(days=1)
            sale_day = start - dt.timedelta(days=2)
            if sale_day > today:
                break
        for member in made:
            people.append(
                Person(
                    member=member,
                    visits_per_week=rng.uniform(2.0, 4.5),
                    morning=member is payer or rng.random() < 0.5,
                    periods=periods[member.id],
                )
            )
    return people


# --- classes (§19.4) ----------------------------------------------------------------


def _covered(person: Person, day: dt.date) -> bool:
    return any(
        p.start <= day <= p.end and not (p.frozen and p.frozen[0] <= day <= p.frozen[1])
        for p in person.periods
    )


def classes(
    db,
    gym: Gym,
    branches: dict[str, Branch],
    kinds: dict[str, ClassType],
    staff: dict[str, StaffUser],
    people: list[Person],
    today: dt.date,
    now: dt.datetime,
) -> int:
    """The timetable, four weeks of classes behind and four ahead: booked from
    the app, a few cancelled late, who came ticked by the instructor; the week
    ahead booked, Saturday's Zumba full with a waitlist."""
    for name, branch, days, starts, teacher in TIMETABLE:
        kind = kinds[name]
        for weekday in days:
            db.add(
                ClassSlot(
                    gym_id=gym.id,
                    branch_id=branches[branch].id,
                    type_id=kind.id,
                    weekday=weekday,
                    starts=starts,
                    minutes=kind.minutes,
                    places=kind.places,
                    instructor_id=staff[teacher].id,
                )
            )
    db.flush()
    # The worker makes each class 4 weeks ahead: as it would have, from 4
    # weeks ago.
    first = today - dt.timedelta(days=28)
    for day in (first, today):
        with happened(at(day, 0, 5)):
            classes_service.generate(db, gym_id=gym.id, today=day)
    teachers = {s.id: staff_context(s, db) for s in staff.values()}
    by_branch: dict[object, list[Person]] = {}
    for person in people:
        if not person.member.is_archived:
            by_branch.setdefault(person.member.home_branch_id, []).append(person)

    from app.models.classes import GymClass

    booked = 0
    week_ahead = now + dt.timedelta(days=7)
    rows = db.scalars(
        select(GymClass)
        .where(GymClass.gym_id == gym.id, GymClass.starts_at <= week_ahead)
        .order_by(GymClass.starts_at)
    ).all()
    for gym_class in rows:
        day = gym_class.starts_at.astimezone(NEPAL).date()
        kind = db.get(ClassType, gym_class.type_id)
        assert kind is not None
        regulars = [
            p for p in by_branch.get(gym_class.branch_id, []) if _covered(p, day)
        ]
        busy = kind.name == "Zumba" and day.weekday() == 5
        wanted = (
            gym_class.places + 3
            if busy
            else int(gym_class.places * rng.uniform(0.35, 0.9))
        )
        past = gym_class.starts_at < now
        made = []
        for person in rng.sample(regulars, min(wanted, len(regulars))):
            # Within the week before, once booking opened, and not after now.
            when = gym_class.starts_at - dt.timedelta(hours=rng.randint(3, 60))
            when = max(when, gym_class.starts_at - dt.timedelta(days=6, hours=23))
            when = min(when, now - dt.timedelta(minutes=rng.randint(1, 50)))
            if when >= gym_class.starts_at - dt.timedelta(minutes=30):
                continue
            try:
                with ExitStack() as stack:
                    stack.enter_context(happened(when))
                    # No reminders for classes long gone.
                    stack.enter_context(
                        patch.object(classes_service, "_remind", lambda *a: None)
                    )
                    booking = classes_service.book(db, gym, person.member, gym_class)
            except AppError:
                continue  # their plan doesn't include it: as the app would say
            dated(db, when, booking)
            made.append(booking)
            booked += 1
        if not past:
            continue
        teacher = teachers[gym_class.instructor_id]
        for booking in made:
            if booking.status != "booked":
                continue
            if rng.random() < 0.06:
                late = rng.random() < 0.5
                when = gym_class.starts_at - dt.timedelta(hours=1 if late else 20)
                if when > booking.booked_at:
                    with happened(when):
                        classes_service.cancel_booking(db, gym, booking, gym_class)
                    continue
            with happened(gym_class.starts_at + dt.timedelta(minutes=50)):
                classes_service.set_attended(
                    db, teacher, booking, gym_class, rng.random() < 0.88
                )
    return booked


# --- progress (§19.5) ----------------------------------------------------------------


def progress(
    db,
    gym: Gym,
    people: list[Person],
    trainers: list[tuple[StaffContext, StaffUser]],
    today: dt.date,
) -> int:
    """Weight and measurements every few weeks for some members: recorded in
    their app, or by a trainer; most losing a little, some building up."""
    candidates = [
        p
        for p in people
        if p.periods and p.periods[-1].end >= today - dt.timedelta(days=20)
    ]
    made = 0
    for person in rng.sample(candidates, min(30, len(candidates))):
        member = person.member
        woman = member.gender == "female"
        member.height_mm = rng.randint(1500, 1700) if woman else rng.randint(1620, 1850)
        weight = rng.uniform(52, 75) if woman else rng.uniform(62, 95)
        trend = rng.choice([-0.9, -0.6, -0.4, -0.2, 0.3])  # kg a month
        fat = rng.uniform(24, 34) if woman else rng.uniform(16, 28)
        waist = rng.uniform(70, 90) if woman else rng.uniform(80, 102)
        measures = rng.random() < 0.6
        trainer = rng.choice(trainers)[1] if rng.random() < 0.4 else None
        day = max(person.periods[0].start, today - dt.timedelta(days=150))
        while day <= today:
            months = (day - person.periods[0].start).days / 30
            kilos = weight + trend * months + rng.uniform(-0.6, 0.6)
            fields: dict = {"measured_on": day, "weight_g": round(kilos * 10) * 100}
            if measures:
                fields["body_fat"] = round((fat + trend * 0.6 * months) * 10)
                fields["waist_mm"] = round((waist + trend * 1.1 * months) * 10)
            with happened(at(day, rng.randint(6, 19), rng.randint(0, 59))):
                progress_service.record(db, member, fields, staff=trainer)
            made += 1
            day += dt.timedelta(days=rng.randint(14, 30))
    db.flush()
    return made


# --- messages sent (§19.3) ----------------------------------------------------------


# What the desk sells (§20.1): name, category, rupees, opening stock, warn at,
# and how many a day go, roughly.
SHELF = [
    ("Whey protein 2 lb", "supplement", 6_500, 8, 3, 0.12),
    ("Whey protein 5 lb", "supplement", 13_500, 4, 2, 0.05),
    ("Mass gainer 3 kg", "supplement", 7_800, 4, 2, 0.04),
    ("Creatine 300 g", "supplement", 4_200, 6, 2, 0.06),
    ("BCAA 30 servings", "supplement", 3_900, 5, 2, 0.04),
    ("Water 1 litre", "drink", 30, 60, 12, 3.2),
    ("Energy drink", "drink", 150, 24, 6, 0.8),
    ("Protein bar", "snack", 250, 30, 8, 0.9),
    ("Shaker bottle", "merchandise", 600, 12, 3, 0.08),
    ("Gym T-shirt", "merchandise", 1_200, 15, 4, 0.06),
    ("Lifting gloves", "merchandise", 1_500, 6, 2, 0.04),
]
SHOP_DAYS = 90


def shop(db, desk: StaffContext, people: list[Person], refs: Refs, today, now) -> int:
    """Three months of the till: protein and water mostly, to members and
    walk-ins, deliveries when stock runs low, and one sale voided."""
    opened = today - dt.timedelta(days=SHOP_DAYS)
    products = []
    with happened(at(opened, 9, 30)):
        for n, (name, category, rupees, stock, low, _) in enumerate(SHELF):
            product = shop_service.create_product(
                db,
                desk,
                {
                    "name": name,
                    "category": category,
                    "price": rupees * 100,
                    "stock": stock,
                    "low_stock": low,
                    "code": f"89{n:04d}{rng.randint(100_000, 999_999)}",
                    "sort_order": n,
                },
                None,
            )
            products.append(product)
    sales = []
    members = [p.member for p in people if not p.member.is_archived]
    for offset in range(SHOP_DAYS):
        day = opened + dt.timedelta(days=offset + 1)
        for product, (_, _, _, stock, low, _) in zip(products, SHELF, strict=True):
            # A delivery the morning after the shelf ran low.
            if product.stock is not None and product.stock <= low:
                with happened(at(day, 8, rng.randint(0, 50))):
                    shop_service.change_stock(
                        db, desk, product, "restock", stock, None, None
                    )
        basket_count = rng.randint(2, 6)
        for _ in range(basket_count):
            moment = desk_time(day, now)
            if moment.date() != day:
                continue
            basket = {}
            for product, (*_, per_day) in zip(products, SHELF, strict=True):
                if rng.random() < per_day / basket_count:
                    left = product.stock if product.stock is not None else 99
                    count = min(left, 1 if per_day < 1 else rng.randint(1, 3))
                    if count > 0:
                        basket[product.id] = count
            if not basket:
                continue
            method = pick(METHODS)
            buyer = rng.choice(members) if rng.random() < 0.7 else None
            with happened(moment):
                sale, payment = shop_service.sell(
                    db,
                    desk,
                    lines=list(basket.items()),
                    member_id=buyer.id if buyer else None,
                    branch_id=None,
                    discount=0,
                    method=method,
                    transaction_ref=refs.new(method),
                    note=None,
                )
            dated(db, moment, sale, payment)
            sales.append(sale)
    # Rung up twice by mistake.
    if sales:
        wrong = sales[-3]
        with happened(wrong.sold_at + dt.timedelta(minutes=4)):
            shop_service.void(db, desk, wrong, "Rung up twice")
    return len(sales)


def messages(db, gym: Gym, people: list[Person], today: dt.date, now) -> int:
    """The last fortnight's reminders: by WhatsApp to members who agreed,
    delivered and mostly read, by SMS to the rest; message credits bought
    and spent."""
    agreed = [p for p in people if rng.random() < 0.45 and not p.member.is_archived]
    for person in agreed:
        person.member.whatsapp_agreed_at = at(person.member.joined_on, 12, 0)
    bought = at(today - dt.timedelta(days=20), 11, 0)
    balance = 1000 + (
        db.scalar(
            select(func.coalesce(func.sum(SmsCreditLedger.change), 0)).where(
                SmsCreditLedger.gym_id == gym.id
            )
        )
        or 0
    )
    db.add(
        SmsCreditLedger(
            gym_id=gym.id,
            change=1000,
            reason="topup:1000",
            balance_after=balance,
            created_at=bought,
        )
    )
    recent = today - dt.timedelta(days=14)
    soon = today + dt.timedelta(days=7)
    ending = [p for p in people if p.periods and recent <= p.periods[-1].end <= soon]
    # A small demo (the tests'): someone, at least.
    ending = ending or [p for p in people if p.periods][:3]
    sent = 0
    for person in ending:
        member = person.member
        end = person.periods[-1].end
        day = min(end - dt.timedelta(days=3), today)
        when = min(at(day, 9, rng.randint(0, 20)), now - dt.timedelta(minutes=5))
        first = member.name.split()[0]
        on_whatsapp = member.whatsapp_agreed_at is not None
        if on_whatsapp:
            body = (
                f"Hi {first}, this is {gym.name}. Your membership ends on "
                f"{format_date(end, gym.config.date_display)}. You can renew at "
                "the desk or in the app."
            )
        else:
            body = f"Hi {first}, 3 days left on your {gym.name} membership. Renew: …"
        message = SmsMessage(
            gym_id=gym.id,
            member_id=member.id,
            to=member.phone,
            body=body,
            kind=SMS_REMINDER,
            status=SMS_SENT,
            provider="console",
            segments=1,
            sent_at=when,
            channel=CHANNEL_WHATSAPP if on_whatsapp else CHANNEL_SMS,
            template="gymbhai_membership_ends" if on_whatsapp else None,
            delivered_at=when + dt.timedelta(seconds=rng.randint(2, 40))
            if on_whatsapp
            else None,
            read_at=when + dt.timedelta(minutes=rng.randint(1, 300))
            if on_whatsapp and rng.random() < 0.8
            else None,
            created_at=when,
        )
        db.add(message)
        db.flush()
        balance -= 1
        db.add(
            SmsCreditLedger(
                gym_id=gym.id,
                change=-1,
                reason=f"{message.channel}:reminder",
                balance_after=balance,
                sms_message_id=message.id,
                created_at=when,
            )
        )
        sent += 1
    db.flush()
    return sent


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
        kinds = class_types(db, gym)
        plans = price_plans(db, gym, kinds)
        # On GymBhai since before its first member: Reports' trends start
        # from the month a gym joined.
        dated(
            db,
            at(year_ago - dt.timedelta(days=3), 9, 0),
            gym,
            owner_row,
            *branches.values(),
            *staff.values(),
            *kinds.values(),
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
        numbers = phones(members + FAMILY_PEOPLE)
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

        people += families(db, gym, desk, plans, branches, numbers, refs, today, now)

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
        say("  classes…")
        booked = classes(db, gym, branches, kinds, staff, people, today, now)
        checks = progress(db, gym, people, trainers, today)
        sold = shop(db, desk, people, refs, today, now)
        sent = messages(db, gym, people, today, now)
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
        "class bookings": booked,
        "progress checks": checks,
        "messages": sent,
        "shop sales": sold,
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
