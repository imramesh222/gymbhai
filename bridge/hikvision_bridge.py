"""The GymBhai bridge for a Hikvision reader (PLAN.md §18.2, docs/READERS.md).

GymBhai can't reach a reader on a gym's own network, so this runs there, on
any PC or Raspberry Pi with Python 3.10 or later and nothing else installed:

    python3 hikvision_bridge.py bridge.json

Every few seconds, for each reader in bridge.json, it

1. collects the changes for the reader from GymBhai and makes them over the
   reader's ISAPI: members put on with the last day it should let them in,
   or taken off;
2. reads the scans from the reader's own event log and passes them on to
   GymBhai, which records them as check-ins under the same rules as a QR scan.

Fingerprints and faces stay on the reader. If the internet drops, the reader
keeps working on what it was last told, and the bridge catches up after.

bridge.json:

    {
      "server": "https://app.gymbhai.com",
      "interval": 5,
      "readers": [
        {"token": "the reader's token from Settings → Door scanners",
         "address": "http://192.168.1.64",
         "username": "admin", "password": "the reader's password"}
      ]
    }

Written to Hikvision's published ISAPI for access control; to be confirmed on
a real reader before a gym relies on it.
"""

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

NEPAL = dt.timezone(dt.timedelta(hours=5, minutes=45))
# ISAPI's access control events (major 5), read this many at a time.
PAGE = 30
# How the reader says someone proved who they were, to GymBhai's words.
HOW = (
    ("face", "face"),
    ("fp", "fingerprint"),
    ("finger", "fingerprint"),
    ("card", "card"),
)


# --- what is said to the reader (ISAPI) ----------------------------------------------


def user_body(command: dict, today: dt.date) -> dict:
    """A member put on the reader, or changed: the reader lets them in until
    the end of `until`, and not at all when there is none (expired, frozen,
    not yet started). Their face and fingerprints stay on it either way."""
    until = command.get("until")
    last = dt.date.fromisoformat(until) if until else today - dt.timedelta(days=1)
    return {
        "UserInfo": {
            "employeeNo": command["pin"],
            "name": command["name"][:32],
            "userType": "normal",
            "Valid": {
                "enable": True,
                "beginTime": "2020-01-01T00:00:00",
                "endTime": f"{last.isoformat()}T23:59:59",
                "timeType": "local",
            },
            "doorRight": "1",
            "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}],
        }
    }


def delete_body(command: dict) -> dict:
    return {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": command["pin"]}]}}


def search_body(since: dt.datetime, now: dt.datetime, position: int) -> dict:
    return {
        "AcsEventCond": {
            "searchID": str(uuid.uuid4()),
            "searchResultPosition": position,
            "maxResults": PAGE,
            "major": 5,
            "minor": 0,
            "startTime": since.astimezone(NEPAL).isoformat(timespec="seconds"),
            "endTime": now.astimezone(NEPAL).isoformat(timespec="seconds"),
        }
    }


def events_from(answer: dict) -> tuple[list[dict], bool]:
    """The scans in an event search's answer, as GymBhai takes them, and
    whether there are more to read."""
    found = answer.get("AcsEvent", {})
    scans = []
    for event in found.get("InfoList", []) or []:
        pin = str(event.get("employeeNoString") or event.get("employeeNo") or "")
        when = event.get("time")
        if not pin or not when:
            continue
        mode = str(event.get("currentVerifyMode", "")).lower()
        how = next((name for key, name in HOW if key in mode), "face")
        scans.append({"pin": pin, "at": when, "how": how})
    return scans, found.get("responseStatusStrg") == "MORE"


# --- talking -------------------------------------------------------------------------


class Reader:
    """One reader on the gym's network, and its token for GymBhai."""

    def __init__(self, server: str, settings: dict) -> None:
        self.server = server.rstrip("/")
        self.token = settings["token"]
        self.address = settings["address"].rstrip("/")
        passwords = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        passwords.add_password(
            None, self.address, settings["username"], settings["password"]
        )
        self.isapi = urllib.request.build_opener(
            urllib.request.HTTPDigestAuthHandler(passwords)
        )

    def gymbhai(self, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"{self.server}/api/v1/kiosk/reader/{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Device-Token": self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as answer:
            return json.load(answer)

    def reader(self, method: str, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            f"{self.address}{path}",
            method=method,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.isapi.open(request, timeout=20) as answer:
            return json.load(answer)

    def make_changes(self, today: dt.date) -> int:
        commands = self.gymbhai("GET", "commands")["commands"]
        results = []
        for command in commands:
            try:
                if command["action"] == "remove":
                    self.reader(
                        "PUT",
                        "/ISAPI/AccessControl/UserInfo/Delete?format=json",
                        delete_body(command),
                    )
                else:
                    self.reader(
                        "PUT",
                        "/ISAPI/AccessControl/UserInfo/SetUp?format=json",
                        user_body(command, today),
                    )
                results.append({"id": command["id"], "ok": True})
            except (urllib.error.URLError, OSError, ValueError) as error:
                results.append({"id": command["id"], "ok": False, "error": str(error)})
        if results:
            self.gymbhai("POST", "results", {"results": results})
        return len(results)

    def pass_scans(self, since: dt.datetime, now: dt.datetime) -> int:
        sent, position, more = 0, 0, True
        while more:
            answer = self.reader(
                "POST",
                "/ISAPI/AccessControl/AcsEvent?format=json",
                search_body(since, now, position),
            )
            scans, more = events_from(answer)
            position += PAGE
            if scans:
                self.gymbhai("POST", "events", {"events": scans})
                sent += len(scans)
        return sent


def run(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text())
    state_path = Path(config_path).with_suffix(".state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    readers = [Reader(config["server"], r) for r in config["readers"]]
    while True:
        now = dt.datetime.now(NEPAL)
        for reader in readers:
            since = dt.datetime.fromisoformat(
                state.get(
                    reader.token[:12], (now - dt.timedelta(minutes=5)).isoformat()
                )
            )
            try:
                made = reader.make_changes(now.date())
                sent = reader.pass_scans(since, now)
                # A minute back each time: GymBhai keeps each scan once.
                state[reader.token[:12]] = (now - dt.timedelta(minutes=1)).isoformat()
                state_path.write_text(json.dumps(state))
                if made or sent:
                    print(
                        f"{now:%H:%M:%S} {reader.address}: {made} changes, {sent} scans"
                    )
            except (urllib.error.URLError, OSError, ValueError) as error:
                print(f"{now:%H:%M:%S} {reader.address}: {error}", file=sys.stderr)
        time.sleep(config.get("interval", 5))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 hikvision_bridge.py bridge.json")
    run(sys.argv[1])
