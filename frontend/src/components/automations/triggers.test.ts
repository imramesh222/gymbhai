import { describe, expect, it } from "vitest";

import { TRIGGERS, when } from "./triggers";

describe("automation triggers", () => {
  it("puts personal training's under their own heading", () => {
    expect(
      TRIGGERS.filter((info) => info.group === "pt").map((i) => i.trigger),
    ).toEqual(["pt_ending", "pt_dues"]);
  });

  it("says when personal training's are sent, as memberships' are", () => {
    expect(when("pt_ending", -3)).toBe("3 days before it ends");
    expect(when("pt_ending", 0)).toBe("On the day it ends");
    expect(when("pt_ending", 1)).toBe("1 day after it ended");
    expect(when("expiry", -1)).toBe("1 day before it ends");
    expect(when("pt_dues", 7)).toBe("7 days after the sale, still owed");
  });
});
