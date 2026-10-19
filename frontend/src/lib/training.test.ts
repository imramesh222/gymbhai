import { describe, expect, it } from "vitest";

import { mayCorrect, mayRecord, sessionsLine } from "./training";

const ME = "staff-1";
const holding =
  (...permissions: string[]) =>
  (permission: string) =>
    permissions.includes(permission);

describe("personal training on the staff screens", () => {
  it("counts down a pack, and counts up monthly training", () => {
    expect(sessionsLine({ sessions: 12, sessions_left: 8, sessions_used: 4 })).toBe(
      "8 of 12 sessions left",
    );
    expect(
      sessionsLine({ sessions: null, sessions_left: null, sessions_used: 5 }),
    ).toBe("5 sessions so far");
    expect(
      sessionsLine({ sessions: null, sessions_left: null, sessions_used: 1 }),
    ).toBe("1 session so far");
  });

  it("lets a trainer record on their own clients, and the desk on anyone's", () => {
    const mine = { trainer_id: ME, status: "active" as const };
    const theirs = { trainer_id: "staff-2", status: "active" as const };
    expect(mayRecord(mine, ME, holding("pt.train"))).toBe(true);
    expect(mayRecord(theirs, ME, holding("pt.train"))).toBe(false);
    expect(mayRecord(theirs, ME, holding("pt.sell"))).toBe(true);
    expect(mayRecord(mine, ME, holding("members.view"))).toBe(false);
  });

  it("records only while it's under way, but corrects mistakes after", () => {
    for (const status of ["upcoming", "used_up", "ended", "cancelled"] as const) {
      expect(mayRecord({ trainer_id: ME, status }, ME, holding("pt.train"))).toBe(
        false,
      );
    }
    expect(mayCorrect({ trainer_id: ME }, ME, holding("pt.train"))).toBe(true);
    expect(mayCorrect({ trainer_id: ME }, undefined, holding("pt.train"))).toBe(false);
  });
});
