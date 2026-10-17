import { describe, expect, it } from "vitest";

import { compact, compactRupees, heatBin, niceTicks } from "./scale";

describe("chart scales", () => {
  it("makes round ticks that reach the maximum", () => {
    expect(niceTicks(87)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(18_500)).toEqual([0, 5000, 10000, 15000, 20000]);
    expect(niceTicks(3)).toEqual([0, 1, 2, 3]);
    // Two visits never get a 0.5 tick.
    expect(niceTicks(2)).toEqual([0, 1, 2]);
    expect(niceTicks(0)).toEqual([0, 1]);
  });

  it("writes big numbers short, the Nepali way", () => {
    expect(compact(950)).toBe("950");
    expect(compact(1_200)).toBe("1.2K");
    expect(compact(340_000)).toBe("3.4L");
    // Money is kept in paisa; its axis is in rupees.
    expect(compactRupees(600_000)).toBe("Rs 6K");
  });

  it("puts nothing in its own bin and the most in the darkest", () => {
    expect(heatBin(0, 40)).toBe(-1);
    expect(heatBin(1, 40)).toBe(0);
    expect(heatBin(40, 40)).toBe(4);
    expect(heatBin(20, 40)).toBe(2);
  });
});
