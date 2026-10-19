import { describe, expect, it } from "vitest";

import { monthName, shiftMonth } from "./months";

describe("months of the gym's calendar", () => {
  it("steps across the end of a year both ways", () => {
    expect(shiftMonth("2083-12", 1)).toBe("2084-01");
    expect(shiftMonth("2083-01", -1)).toBe("2082-12");
    expect(shiftMonth("2026-10", -12)).toBe("2025-10");
  });

  it("names BS and AD months", () => {
    expect(monthName("2083-07", "bs", true)).toBe("Kartik 2083");
    expect(monthName("2026-10", "ad")).toBe("Oct");
  });
});
