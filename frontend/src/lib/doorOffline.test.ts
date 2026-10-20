import { describe, expect, it } from "vitest";

import cases from "@shared/door/cases.json";
import { decideOffline, withinHours, type RosterMember } from "@shared/door/offline";

/** The kiosk with no internet (PLAN.md §19.2). */

const FROM = "2026-10-20";

function member(fields: Partial<RosterMember>): RosterMember {
  return {
    id: "m1",
    name: "Sita Rai",
    code: "FZ-1",
    photo: null,
    photo_url: null,
    card: "",
    key: "",
    days: "a".repeat(14),
    hours: null,
    visits_left: null,
    owes: false,
    plan_name: "1 month",
    valid_until: "2026-11-19",
    ...fields,
  };
}

const atNepal = (date: string, time: string) => Date.parse(`${date}T${time}:00+05:45`);

describe("the kiosk decides as the server's door does", () => {
  // Written by the server's tests/integration/test_offline_kiosk.py.
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const decision = decideOffline(
      member({
        days: c.days,
        hours: c.hours as RosterMember["hours"],
        visits_left: c.visits_left,
        owes: c.owes,
      }),
      { from_date: FROM, rules: c.rules as never },
      atNepal(FROM, c.time),
    );
    expect({ result: decision.result, reason: decision.reason }).toEqual(c.expected);
  });
});

describe("what only the kiosk knows", () => {
  const rules = { grace_days: 0, rescan_minutes: 180, dues_rule: "warn" as const };
  const now = atNepal(FROM, "08:00");

  it("counts the visits it let in since the roster came", () => {
    const pack = member({ visits_left: 2 });
    expect(decideOffline(pack, { from_date: FROM, rules }, now, 1).result).toBe(
      "allowed",
    );
    expect(decideOffline(pack, { from_date: FROM, rules }, now, 2).result).toBe(
      "denied_visits_used",
    );
  });

  it("says already checked in within the re-scan window", () => {
    const sita = member({});
    const earlier = now - 60 * 60 * 1000;
    const again = decideOffline(sita, { from_date: FROM, rules }, now, 0, earlier);
    expect(again).toEqual({ result: "duplicate", reason: null, let_in: true });
    const later = now - 4 * 60 * 60 * 1000;
    expect(decideOffline(sita, { from_date: FROM, rules }, now, 0, later).result).toBe(
      "allowed",
    );
  });

  it("reads the right day's letter, and sends anyone past the roster to the desk", () => {
    const starts = member({ days: "xxaaaaaaaaaaaa" });
    const roster = { from_date: FROM, rules };
    expect(decideOffline(starts, roster, now).result).toBe("denied_expired");
    expect(decideOffline(starts, roster, atNepal("2026-10-22", "08:00")).result).toBe(
      "allowed",
    );
    expect(decideOffline(starts, roster, atNepal("2026-11-30", "08:00")).result).toBe(
      "denied_expired",
    );
  });

  it("tells the hour in Nepal, whatever the device's time zone", () => {
    const mornings = [{ days: [0, 1, 2, 3, 4, 5, 6], from: "06:00", to: "10:00" }];
    // 03:00 UTC is 08:45 in Kathmandu.
    expect(withinHours(mornings, Date.parse("2026-10-20T03:00:00Z"))).toBe(true);
    expect(withinHours(mornings, Date.parse("2026-10-20T05:00:00Z"))).toBe(false);
  });
});
