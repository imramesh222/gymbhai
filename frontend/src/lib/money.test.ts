import { describe, expect, it } from "vitest";

import { formatRs, parseRs, toInput } from "./money";

describe("money", () => {
  it("uses Nepali grouping", () => {
    expect(formatRs(1_00_000_00)).toBe("Rs 1,00,000");
    expect(formatRs(1500_50)).toBe("Rs 1,500.5");
    expect(formatRs(-200_00)).toBe("−Rs 200");
    expect(formatRs(null)).toBe("—");
  });

  it("parses what people type into paisa", () => {
    expect(parseRs("1,500")).toBe(1500_00);
    expect(parseRs("Rs 1500.5")).toBe(1500_50);
    expect(parseRs("")).toBeNull();
    expect(parseRs("12.345")).toBeNull();
    expect(parseRs("abc")).toBeNull();
  });

  it("round-trips through an input box", () => {
    expect(toInput(1500_00)).toBe("1500");
    expect(toInput(1500_50)).toBe("1500.50");
  });
});
