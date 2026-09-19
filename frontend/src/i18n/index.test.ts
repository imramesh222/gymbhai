import { describe, expect, it } from "vitest";

import { isMessageKey, plural, t } from "./index";

describe("t", () => {
  it("returns the English text", () => {
    expect(t("app.name")).toBe("GymBhai");
  });

  it("fills in variables and leaves unknown ones visible", () => {
    expect(t("staff.welcome", { name: "Sita" })).toBe("Welcome, Sita");
    expect(t("staff.welcome")).toBe("Welcome, {name}");
  });

  it("recognises keys built at runtime", () => {
    expect(isMessageKey("errors.slug_taken")).toBe(true);
    expect(isMessageKey("errors.no_such_code")).toBe(false);
  });

  it("picks the plural form", () => {
    expect(plural(1, "staff.trialDaysLeft.one", "staff.trialDaysLeft.other")).toBe(
      "1 day left in your free trial.",
    );
    expect(plural(9, "staff.trialDaysLeft.one", "staff.trialDaysLeft.other")).toBe(
      "9 days left in your free trial.",
    );
  });
});
