import { describe, expect, it } from "vitest";

import type { Plan } from "./api";
import { bestValue, perMonth, savings } from "./planValue";

const plan = (
  months: number | null,
  price: number | null,
  days: number | null = null,
) =>
  ({
    id: `${months}-${days}-${price}`,
    duration_months: months,
    duration_days: days,
    price,
  }) as Plan;

describe("plan value", () => {
  const monthly = plan(1, 1500_00);
  const quarter = plan(3, 4000_00);
  const year = plan(12, 18000_00); // no cheaper than monthly
  const day = plan(null, 300_00, 1);
  const plans = [monthly, quarter, year, day];

  it("shows the price a month for plans in months", () => {
    expect(perMonth(quarter)).toBe(1333_33);
    expect(perMonth(monthly)).toBe(1500_00);
    expect(perMonth(day)).toBeNull();
    expect(perMonth(plan(3, null))).toBeNull();
  });

  it("shows savings only where there are some", () => {
    expect(savings(quarter, plans)).toBe(500_00);
    expect(savings(year, plans)).toBeNull();
    expect(savings(monthly, plans)).toBeNull();
    expect(savings(day, plans)).toBeNull();
    expect(savings(quarter, [quarter])).toBeNull(); // nothing to compare with
  });

  it("marks the plan that saves the most for its price", () => {
    const half = plan(6, 7000_00); // saves 2000 of 9000: more than the quarter
    expect(bestValue([...plans, half])).toBe(half.id);
    expect(bestValue(plans)).toBe(quarter.id);
    expect(bestValue([monthly, year, day])).toBeNull();
  });

  it("compares only plans of the same kind", () => {
    // A gym like the demo one: a visit pack and a morning-only month are the
    // cheapest one-month plans, but not what 3 months is compared with.
    const pack = { ...plan(1, 1000_00), visit_limit: 10 } as Plan;
    const morning = {
      ...plan(1, 1200_00),
      access_hours: [{ days: [0], from: "06:00", to: "10:00" }],
    } as Plan;
    const couple = { ...plan(12, 30000_00), seats: 2 } as Plan;
    const all = [monthly, quarter, pack, morning, couple];
    expect(savings(quarter, all)).toBe(500_00); // against 1,500 a month
    expect(savings(couple, all)).toBeNull(); // no couple's month to compare
    const morningQuarter = { ...morning, duration_months: 3, price: 3000_00 } as Plan;
    expect(savings(morningQuarter, [...all, morningQuarter])).toBe(600_00);
  });
});
