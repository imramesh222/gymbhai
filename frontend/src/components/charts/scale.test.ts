import { describe, expect, it } from "vitest";

import { niceRange } from "@shared/niceRange";

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

describe("niceRange: a line's scale fitted to its values (§19.5)", () => {
  it("spans the values with round steps, fractions allowed", () => {
    expect(niceRange(61.5, 64)).toEqual([61, 62, 63, 64]);
    expect(niceRange(62.1, 62.9)).toEqual([62, 62.2, 62.4, 62.6, 62.8, 63]);
    const ticks = niceRange(58.2, 72.9);
    expect(ticks[0]).toBeLessThanOrEqual(58.2);
    expect(ticks.at(-1)).toBeGreaterThanOrEqual(72.9);
  });

  it("gives one value a little room either side", () => {
    const ticks = niceRange(62, 62);
    expect(ticks[0]).toBeLessThan(62);
    expect(ticks.at(-1)).toBeGreaterThan(62);
  });
});
