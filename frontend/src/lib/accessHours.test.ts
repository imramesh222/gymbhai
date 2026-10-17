import { describe, expect, it } from "vitest";

import { describeDays, describeHours } from "./accessHours";

describe("access hours", () => {
  it("reads like a sign on the door", () => {
    expect(describeDays([0, 1, 2, 3, 4])).toBe("Mon–Fri");
    expect(describeDays([5, 6])).toBe("Sat, Sun");
    expect(describeDays([6, 0, 1, 2, 3, 4, 5])).toBe("Every day");
    expect(describeDays([0, 2, 3, 4])).toBe("Mon, Wed–Fri");
    expect(
      describeHours([
        { days: [0, 1, 2, 3, 4], from: "06:00", to: "10:00" },
        { days: [5], from: "14:00", to: "17:00" },
      ]),
    ).toBe("Mon–Fri 06:00–10:00; Sat 14:00–17:00");
    expect(describeHours(null)).toBeNull();
  });
});
