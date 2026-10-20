"""The Hikvision bridge's words to the reader and back (bridge/, PLAN.md §18.2).

It runs at the gym, not here: these check what it would say over ISAPI, and
how it reads the reader's event log, without a reader.
"""

import datetime as dt
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[3] / "bridge" / "hikvision_bridge.py"
spec = importlib.util.spec_from_file_location("hikvision_bridge", PATH)
assert spec is not None and spec.loader is not None
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

TODAY = dt.date(2026, 10, 20)


def test_a_member_is_let_in_until_their_last_day() -> None:
    body = bridge.user_body(
        {
            "id": 3,
            "action": "set",
            "pin": "48",
            "name": "Sita Rai",
            "until": "2026-11-17",
        },
        TODAY,
    )
    user = body["UserInfo"]
    assert (user["employeeNo"], user["name"]) == ("48", "Sita Rai")
    assert user["Valid"]["enable"] is True
    assert user["Valid"]["endTime"] == "2026-11-17T23:59:59"


def test_with_no_last_day_the_reader_refuses_them_from_today() -> None:
    """Expired, frozen or not started: kept on the reader, faces and all."""
    body = bridge.user_body(
        {"id": 4, "action": "set", "pin": "48", "name": "Sita Rai", "until": None},
        TODAY,
    )
    assert body["UserInfo"]["Valid"]["endTime"] == "2026-10-19T23:59:59"


def test_taking_someone_off() -> None:
    assert bridge.delete_body({"pin": "48"}) == {
        "UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": "48"}]}
    }


def test_reading_the_event_log() -> None:
    answer = {
        "AcsEvent": {
            "responseStatusStrg": "MORE",
            "InfoList": [
                {
                    "major": 5,
                    "minor": 75,
                    "time": "2026-10-20T06:15:22+05:45",
                    "employeeNoString": "48",
                    "currentVerifyMode": "cardOrFaceOrFp",
                },
                {
                    "major": 5,
                    "minor": 38,
                    "time": "2026-10-20T06:20:01+05:45",
                    "employeeNoString": "52",
                    "currentVerifyMode": "fpOrPw",
                },
                # The door opened by a button: nobody to check in.
                {"major": 5, "minor": 21, "time": "2026-10-20T06:21:00+05:45"},
            ],
        }
    }
    scans, more = bridge.events_from(answer)
    assert more is True
    assert scans == [
        {"pin": "48", "at": "2026-10-20T06:15:22+05:45", "how": "face"},
        {"pin": "52", "at": "2026-10-20T06:20:01+05:45", "how": "fingerprint"},
    ]
    assert bridge.events_from({"AcsEvent": {"responseStatusStrg": "NO MATCH"}}) == (
        [],
        False,
    )


def test_the_search_asks_for_access_events_in_nepal_time() -> None:
    since = dt.datetime(2026, 10, 20, 0, 30, tzinfo=dt.UTC)
    body = bridge.search_body(since, since + dt.timedelta(minutes=5), 30)
    cond = body["AcsEventCond"]
    assert (cond["major"], cond["searchResultPosition"]) == (5, 30)
    assert cond["startTime"] == "2026-10-20T06:15:00+05:45"
