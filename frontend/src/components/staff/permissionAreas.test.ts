import { describe, expect, it } from "vitest";

import { areasOf } from "./permissionAreas";

describe("the staff form's permission areas", () => {
  it("has Enquiries, Personal training and Expenses in their places", () => {
    const areas = areasOf({ permissions: [] });
    expect(areas.slice(0, 2)).toEqual(["members", "leads"]);
    expect(areas.indexOf("pt")).toBe(areas.indexOf("memberships") + 1);
    expect(areas.indexOf("expenses")).toBe(areas.indexOf("payments") + 1);
  });

  it("never leaves out an area it doesn't know", () => {
    const areas = areasOf({
      permissions: [{ area: "members" }, { area: "classes" }, { area: "classes" }],
    });
    expect(areas.at(-1)).toBe("classes");
    expect(areas.filter((a) => a === "classes")).toHaveLength(1);
  });
});
