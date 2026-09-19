import { describe, expect, it } from "vitest";

import { isGsm, smsParts } from "./sms";

describe("smsParts matches the backend", () => {
  it("GSM: 160, then 153 a part", () => {
    expect(smsParts("a".repeat(160))).toBe(1);
    expect(smsParts("a".repeat(161))).toBe(2);
    expect(smsParts("a".repeat(307))).toBe(3);
  });

  it("Nepali: 70, then 67 a part", () => {
    const namaste = "नमस्ते";
    expect(isGsm(namaste)).toBe(false);
    expect(smsParts(namaste.repeat(11) + "न")).toBe(1);
    expect(smsParts(namaste.repeat(12))).toBe(2);
  });

  it("one Nepali letter turns a message Unicode", () => {
    expect(smsParts("a".repeat(100))).toBe(1);
    expect(smsParts("a".repeat(100) + "न")).toBe(2);
  });
});
