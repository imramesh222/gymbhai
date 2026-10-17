import { describe, expect, it } from "vitest";

import type { Plan } from "./api";
import { perMonth, savings } from "./planValue";

const plan = (
  months: number | null,
  price: number | null,
  days: number | null = null,
) => ({ duration_months: months, duration_days: days, price }) as Plan;

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
});
