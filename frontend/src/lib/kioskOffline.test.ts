import { beforeEach, describe, expect, it } from "vitest";

import type { Roster, RosterMember } from "@shared/door/offline";
import { sha256, toHex, utf8 } from "@shared/qr/hmac";

import { sign } from "./ed25519";
import { decide, keepRoster, markSent, tooOld, waiting } from "./kioskOffline";
import { memberCode } from "./memberQr";

/** The kiosk with no internet (PLAN.md §19.2). */

// The shared test vector (backend/tests/unit/test_qr.py).
const HEX = "12345678123456781234567812345678";
const IDENTITY = {
  member_hex: HEX,
  key: "P-5VXu9nLNLOU1OTAEFX9jwIldfaTzZeyqhp38H3WLg",
  version: 1,
  window_seconds: 30,
  signing_key: "mtbJK1LD-vbZuDVIEk8nqscuQojfRzEG9KZys-cjASc",
};
const SITA: RosterMember = {
  id: "12345678-1234-5678-1234-567812345678",
  name: "Sita Rai",
  code: "FZ-1",
  photo: null,
  photo_url: null,
  card: toHex(sha256(utf8("cardtoken123"))),
  key: "p6tHitkllt09ERnscZwAyjqc2nL8DGBHkUO5H1VwTfQ",
  days: "a".repeat(14),
  hours: null,
  visits_left: 5,
  owes: false,
  plan_name: "1 month",
  valid_until: "2026-11-19",
};
const NOW = Date.parse("2026-10-20T08:00:00+05:45");

function roster(): Roster {
  return {
    branch_id: "b1",
    from_date: "2026-10-20",
    server_time: new Date(NOW).toISOString(),
    offline_days: 3,
    rules: { grace_days: 0, rescan_minutes: 180, dues_rule: "warn" },
    members: [SITA],
  };
}

beforeEach(() => localStorage.clear());

describe("the kiosk offline", () => {
  it("lets a member in from a gb2 code, and keeps the scan to send", () => {
    const stored = keepRoster(roster(), NOW);
    const first = decide(memberCode(IDENTITY, NOW, sign), stored, NOW);
    expect(first.result).toMatchObject({
      result: "allowed",
      let_in: true,
      member_name: "Sita Rai",
      days_left: 31,
      visits_left: 4,
    });
    const again = decide(
      memberCode(IDENTITY, NOW + 60_000, sign),
      stored,
      NOW + 60_000,
    );
    expect(again.result.result).toBe("duplicate");
    expect(waiting().map((s) => s.result)).toEqual(["allowed", "duplicate"]);

    markSent([first.queued!.client_id]);
    expect(waiting()).toHaveLength(1);
  });

  it("reads a printed card by its hash", () => {
    const stored = keepRoster(roster(), NOW);
    expect(decide("gbc.cardtoken123", stored, NOW).result.member_code).toBe("FZ-1");
    expect(decide("gbc.someoneelse99", stored, NOW).result.result).toBe("unknown");
  });

  it("can't check an old app's gb1 code, nor a forged one", () => {
    const stored = keepRoster(roster(), NOW);
    expect(decide(memberCode(IDENTITY, NOW), stored, NOW).result.reason).toBe(
      "needs_internet",
    );
    const code = memberCode(IDENTITY, NOW, sign);
    expect(decide(code.slice(0, -2) + "AA", stored, NOW).result.result).toBe("unknown");
    expect(waiting()).toEqual([]);
  });

  it("stops after the gym's offline days, on the server's clock", () => {
    // This device's clock runs an hour slow: the roster's time still counts.
    const stored = keepRoster(roster(), NOW - 60 * 60 * 1000);
    expect(tooOld(stored, NOW + 2 * 24 * 60 * 60 * 1000)).toBe(false);
    const late = NOW + 3 * 24 * 60 * 60 * 1000;
    expect(tooOld(stored, late)).toBe(true);
    expect(decide(memberCode(IDENTITY, late, sign), stored, late).result.reason).toBe(
      "offline_too_long",
    );
  });
});
