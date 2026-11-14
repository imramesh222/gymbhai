import { describe, expect, it } from "vitest";

import { memberAppUrl, slugify } from "./slug";

describe("memberAppUrl", () => {
  it("is the gym's address at this site's", () => {
    expect(memberAppUrl("gymbhai.com.np", "fitness-zone")).toBe(
      "gymbhai.com.np/fitness-zone",
    );
    expect(memberAppUrl("localhost:3000", "")).toBe("localhost:3000/…");
  });
});

describe("slugify", () => {
  it.each([
    ["Fitness Zone", "fitness-zone"],
    ["  Iron House Gym & Spa ", "iron-house-gym-spa"],
    ["Café Fit", "cafe-fit"],
    ["Gym 42 -- Baneshwor", "gym-42-baneshwor"],
  ])("%s -> %s", (name, slug) => {
    expect(slugify(name)).toBe(slug);
  });

  it("never ends in a hyphen after truncating", () => {
    const slug = slugify("a".repeat(39) + " b");
    expect(slug.length).toBeLessThanOrEqual(40);
    expect(slug.endsWith("-")).toBe(false);
  });
});
