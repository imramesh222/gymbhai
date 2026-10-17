import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { enterMovesOn } from "./forms";

describe("enterMovesOn", () => {
  it("moves to the next field, and submits from the last", async () => {
    const user = userEvent.setup();
    const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onKeyDown={enterMovesOn} onSubmit={submit}>
        <input aria-label="Name" />
        <input aria-label="Phone" />
        <button type="submit">Save</button>
      </form>,
    );
    // jsdom has no layout: every element counts as shown.
    Object.defineProperty(HTMLElement.prototype, "offsetParent", {
      configurable: true,
      get: () => document.body,
    });
    await user.click(screen.getByLabelText("Name"));
    await user.keyboard("Sita{Enter}");
    expect(screen.getByLabelText("Phone")).toHaveFocus();
    expect(submit).not.toHaveBeenCalled();
    await user.keyboard("98{Enter}");
    expect(submit).toHaveBeenCalled();
  });
});
