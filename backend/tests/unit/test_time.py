import datetime as dt

from app.core.time import today_in_nepal


def test_nepal_is_already_tomorrow_late_in_the_utc_evening() -> None:
    # 18:15 UTC is exactly midnight in Nepal (+05:45).
    assert today_in_nepal(dt.datetime(2026, 9, 19, 18, 14, tzinfo=dt.UTC)) == dt.date(
        2026, 9, 19
    )
    assert today_in_nepal(dt.datetime(2026, 9, 19, 18, 15, tzinfo=dt.UTC)) == dt.date(
        2026, 9, 20
    )
