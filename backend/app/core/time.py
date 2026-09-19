"""Time in Nepal.

Timestamps are stored in UTC. Anything a person thinks of as a day — "today",
a membership's end date, a report month — is a day in Asia/Kathmandu (+05:45),
never the server's local day. At 23:00 UTC it is already tomorrow in Nepal.
"""

import datetime as dt
from zoneinfo import ZoneInfo

NEPAL = ZoneInfo("Asia/Kathmandu")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def today_in_nepal(now: dt.datetime | None = None) -> dt.date:
    return (now or utcnow()).astimezone(NEPAL).date()
