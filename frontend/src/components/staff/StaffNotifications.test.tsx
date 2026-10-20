import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StaffPush } from "@/lib/staffPush";

import { NotificationsCard } from "./StaffNotifications";

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock("@/lib/staffPush", () => ({ useStaffPush: hook }));

function push(over: Partial<StaffPush> = {}): StaffPush {
  return {
    state: "off",
    kinds: ["payment_request", "freeze_request", "lead"],
    muted: [],
    error: null,
    on: vi.fn(() => Promise.resolve()),
    off: vi.fn(() => Promise.resolve()),
    choose: vi.fn(() => Promise.resolve()),
    ...over,
  };
}

describe("My account → Notifications", () => {
  beforeEach(() => hook.mockReset());

  it("turns this device on, with every kind they may get ticked", async () => {
    const current = push();
    hook.mockReturnValue(current);
    render(<NotificationsCard />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Off for this phone or computer.",
    );
    for (const label of [
      "Payments sent from the app, to approve",
      "Freeze requests",
      "Enquiries from the join form",
    ]) {
      expect(screen.getByRole("checkbox", { name: label })).toBeChecked();
    }
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    expect(current.on).toHaveBeenCalledTimes(1);
  });

  it("keeps the ticks as what's turned off", async () => {
    const current = push({ state: "on", muted: ["lead"] });
    hook.mockReturnValue(current);
    render(<NotificationsCard />);
    expect(
      screen.getByRole("checkbox", { name: "Enquiries from the join form" }),
    ).not.toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Freeze requests" }));
    expect(current.choose).toHaveBeenCalledWith(["lead", "freeze_request"]);
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Enquiries from the join form" }),
    );
    expect(current.choose).toHaveBeenLastCalledWith([]);
    await userEvent.click(screen.getByRole("button", { name: "Turn off" }));
    expect(current.off).toHaveBeenCalledTimes(1);
  });

  it("says why it can't be on, and what to do", () => {
    hook.mockReturnValue(push({ state: "install" }));
    render(<NotificationsCard />);
    expect(screen.getByRole("status")).toHaveTextContent(
      /add GymBhai to your Home Screen/,
    );
    expect(screen.queryByRole("button", { name: "Turn on" })).toBeNull();
  });

  it("isn't shown to staff whose permissions show none of them", () => {
    hook.mockReturnValue(push({ kinds: [] }));
    const { container } = render(<NotificationsCard />);
    expect(container).toBeEmptyDOMElement();
  });
});
