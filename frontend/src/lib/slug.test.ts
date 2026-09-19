import { describe, expect, it } from "vitest";

import { slugify } from "./slug";

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
