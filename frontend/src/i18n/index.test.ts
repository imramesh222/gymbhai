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

describe("the English catalog", () => {
  it("has no key twice: JSON keeps only the last one, silently", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const raw = readFileSync(resolve(process.cwd(), "src/i18n/en.json"), "utf8");
    const keys = [...raw.matchAll(/^\s*"([^"]+)"\s*:/gm)].map((m) => m[1]);
    const seen = new Set<string>();
    const repeated = keys.filter((key) => seen.has(key) || !seen.add(key));
    expect(repeated).toEqual([]);
  });
});

describe("the Nepali catalog", () => {
  it("has every English key, with the same placeholders", async () => {
    const en = (await import("./en.json")).default as Record<string, string>;
    const ne = (await import("./ne.json")).default as Record<string, string>;
    expect(Object.keys(ne).sort()).toEqual(Object.keys(en).sort());
    const slots = (text: string) =>
      [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    const different = Object.keys(en).filter(
      (key) => slots(en[key]).join() !== slots(ne[key] ?? "").join(),
    );
    expect(different).toEqual([]);
  });
});

describe("switching language", () => {
  it("speaks Nepali, with Nepali digits only when the gym asks for them", async () => {
    const { setLocale, localDigits } = await import("./index");
    setLocale("ne");
    expect(t("members.daysLeft", { count: 23 })).toBe("23 दिन बाँकी");
    setLocale("ne", "nepali");
    expect(t("members.daysLeft", { count: 23 })).toBe("२३ दिन बाँकी");
    expect(localDigits("2083-07-01")).toBe("२०८३-०७-०१");
    setLocale("en", "nepali");
    expect(t("members.daysLeft", { count: 23 })).toBe("23 days left");
    expect(localDigits("2083")).toBe("2083");
  });
});
