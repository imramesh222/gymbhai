import { describe, expect, it } from "vitest";

import { formatDate, fromBs, planEnd, toBs, todayInNepal } from "./dates";

const months = (n: number) => ({ duration_months: n, duration_days: null });

describe("BS dates", () => {
  it("converts both ways", () => {
    expect(toBs("2026-09-19")).toEqual({ year: 2083, month: 6, day: 3 });
    expect(fromBs({ year: 2083, month: 1, day: 5 })).toBe("2026-04-18");
  });

  it("round-trips every day for two years", () => {
    let day = "2025-01-01";
    for (let i = 0; i < 730; i++) {
      expect(fromBs(toBs(day))).toBe(day);
      day = new Date(Date.parse(day) + 86400000).toISOString().slice(0, 10);
    }
  });
});

describe("plan end dates match the backend", () => {
  it("AD example from the plan", () => {
    expect(planEnd("2026-01-15", months(3), "ad")).toBe("2026-04-14");
  });

  it("BS example from the plan: 5 Baisakh + 3 months ends 4 Shrawan", () => {
    const end = planEnd(fromBs({ year: 2083, month: 1, day: 5 }), months(3), "bs");
    expect(toBs(end)).toEqual({ year: 2083, month: 4, day: 4 });
  });

  it("runs to the end of a shorter month", () => {
    expect(planEnd("2026-01-31", months(1), "ad")).toBe("2026-02-28");
  });

  it("day plans", () => {
    expect(
      planEnd("2026-09-19", { duration_months: null, duration_days: 1 }, "ad"),
    ).toBe("2026-09-19");
  });
});

describe("formatting", () => {
  it("follows the gym's choice", () => {
    expect(formatDate("2026-09-19", "ad")).toBe("19 Sep 2026");
    expect(formatDate("2026-09-19", "bs")).toBe("3 Asoj 2083");
    expect(formatDate("2026-09-19", "both")).toBe("3 Asoj 2083 (19 Sep 2026)");
  });

  it("knows it is already tomorrow in Nepal", () => {
    expect(todayInNepal(new Date("2026-09-19T18:14:00Z"))).toBe("2026-09-19");
    expect(todayInNepal(new Date("2026-09-19T18:15:00Z"))).toBe("2026-09-20");
  });
});
