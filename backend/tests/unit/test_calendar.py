import datetime as dt

import pytest

from app.core.calendar import (
    days_in_bs_month,
    format_date,
    from_bs,
    plan_end_date,
    to_bs,
)


def end(start: dt.date, months: int, calendar: str) -> dt.date:
    return plan_end_date(start, months=months, days=None, calendar=calendar)


def test_ad_example_from_the_plan() -> None:
    # PLAN.md §5.1: a 3-month plan from 15 January ends 14 April.
    assert end(dt.date(2026, 1, 15), 3, "ad") == dt.date(2026, 4, 14)


def test_bs_example_from_the_plan() -> None:
    # PLAN.md §5.1: from 5 Baisakh ends 4 Shrawan.
    assert to_bs(end(from_bs(2083, 1, 5), 3, "bs")) == (2083, 4, 4)


def test_bs_months_are_not_thirty_days() -> None:
    lengths = {days_in_bs_month(2083, m) for m in range(1, 13)}
    assert lengths - {30}, "BS months vary between 29 and 32 days"
    start = from_bs(2083, 1, 1)
    assert end(start, 1, "bs") == start + dt.timedelta(
        days=days_in_bs_month(2083, 1) - 1
    )


def test_a_day_the_target_month_lacks_runs_to_its_end() -> None:
    assert end(dt.date(2026, 1, 31), 1, "ad") == dt.date(2026, 2, 28)
    assert end(dt.date(2028, 1, 31), 1, "ad") == dt.date(2028, 2, 29)


@pytest.mark.parametrize("calendar", ["ad", "bs"])
def test_a_year_crosses_the_year_boundary(calendar: str) -> None:
    start = dt.date(2026, 9, 19)
    finish = end(start, 12, calendar)
    assert 363 <= (finish - start).days <= 366


def test_day_plans() -> None:
    assert plan_end_date(
        dt.date(2026, 9, 19), months=None, days=1, calendar="bs"
    ) == dt.date(2026, 9, 19)


def test_round_trip_every_day_for_two_years() -> None:
    day = dt.date(2025, 1, 1)
    while day < dt.date(2027, 1, 1):
        assert from_bs(*to_bs(day)) == day
        day += dt.timedelta(days=1)


def test_formats() -> None:
    day = dt.date(2026, 9, 19)
    assert format_date(day, "ad") == "19 Sep 2026"
    assert format_date(day, "bs") == "3 Asoj 2083"
    assert format_date(day, "both") == "3 Asoj 2083 (19 Sep 2026)"
