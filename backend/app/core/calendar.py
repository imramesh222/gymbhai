"""AD and BS dates (PLAN.md §5.1, §10).

Dates are always stored in AD. Each gym chooses whether plan months are
counted in AD or BS months, and BS months are 29 to 32 days long and differ
year to year, so BS counting walks the real BS calendar rather than assuming
30 days a month.

A plan of N months starting on day D ends the day before day D of the month N
months later: 15 January + 3 months ends 14 April; 5 Baisakh + 3 months ends
4 Shrawan. When that day does not exist in the target month (31 January + 1
month), the plan runs to the end of the shorter month.
"""

import datetime as dt
from typing import Literal

import nepali_datetime as nd

Calendar = Literal["ad", "bs"]

BS_MONTHS = (
    "Baisakh",
    "Jestha",
    "Asar",
    "Shrawan",
    "Bhadra",
    "Asoj",
    "Kartik",
    "Mangsir",
    "Poush",
    "Magh",
    "Falgun",
    "Chaitra",
)
BS_MIN_YEAR = nd.MINYEAR
BS_MAX_YEAR = nd.MAXYEAR


def to_bs(day: dt.date) -> tuple[int, int, int]:
    bs = nd.date.from_datetime_date(day)
    return bs.year, bs.month, bs.day


def from_bs(year: int, month: int, day: int) -> dt.date:
    return nd.date(year, month, day).to_datetime_date()


def days_in_bs_month(year: int, month: int) -> int:
    return nd._days_in_month(year, month)


def _days_in_ad_month(year: int, month: int) -> int:
    following = dt.date(year + month // 12, month % 12 + 1, 1)
    return (following - dt.timedelta(days=1)).day


def _shift(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def add_months(start: dt.date, months: int, calendar: Calendar) -> dt.date:
    """The same day-of-month `months` later, in the given calendar.

    If that day does not exist, the first day of the month after it — so the
    plan's last day, the day before, is the end of the shorter month.
    """
    if calendar == "ad":
        year, month = _shift(start.year, start.month, months)
        if start.day <= _days_in_ad_month(year, month):
            return dt.date(year, month, start.day)
        next_year, next_month = _shift(year, month, 1)
        return dt.date(next_year, next_month, 1)

    y, m, d = to_bs(start)
    year, month = _shift(y, m, months)
    if d <= days_in_bs_month(year, month):
        return from_bs(year, month, d)
    next_year, next_month = _shift(year, month, 1)
    return from_bs(next_year, next_month, 1)


def plan_end_date(
    start: dt.date,
    *,
    months: int | None,
    days: int | None,
    calendar: Calendar,
) -> dt.date:
    """The last day (inclusive) of a plan starting on `start`."""
    if months:
        return add_months(start, months, calendar) - dt.timedelta(days=1)
    if days:
        return start + dt.timedelta(days=days - 1)
    raise ValueError("A plan needs a duration in months or days.")


def format_bs(day: dt.date) -> str:
    """'4 Shrawan 2083'."""
    y, m, d = to_bs(day)
    return f"{d} {BS_MONTHS[m - 1]} {y}"


def format_ad(day: dt.date) -> str:
    """'19 Sep 2026'."""
    return f"{day.day} {day.strftime('%b %Y')}"


def format_date(day: dt.date, display: Literal["ad", "bs", "both"]) -> str:
    """A date the way the gym has chosen to show dates (SMS, receipts)."""
    if display == "ad":
        return format_ad(day)
    if display == "bs":
        return format_bs(day)
    return f"{format_bs(day)} ({format_ad(day)})"


def bs_table() -> dict:
    """Month lengths for every BS year, for the frontend's converter."""
    return {
        "epoch": {
            "bs": [BS_MIN_YEAR, 1, 1],
            "ad": from_bs(BS_MIN_YEAR, 1, 1).isoformat(),
        },
        "months": BS_MONTHS,
        "years": {
            year: [days_in_bs_month(year, month) for month in range(1, 13)]
            for year in range(BS_MIN_YEAR, BS_MAX_YEAR + 1)
        },
    }
