import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlanMonthsQuestion } from "./PlanMonthsQuestion";

const { update, refreshMe, can } = vi.hoisted(() => ({
  update: vi.fn(),
  refreshMe: vi.fn(),
  can: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  gymApi: { update },
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ can, refreshMe }) }));

describe("how the gym counts plan months", () => {
  beforeEach(() => {
    update.mockReset().mockResolvedValue({});
    refreshMe.mockReset().mockResolvedValue(undefined);
    can.mockReset().mockReturnValue(true);
  });

  it("explains each choice with a member's dates and saves the one picked", async () => {
    const user = userEvent.setup();
    render(<PlanMonthsQuestion />);
    expect(
      screen.getByText(/joins on 5 Baisakh for 3 months stays until 4 Shrawan/),
    ).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    await user.click(screen.getByLabelText(/AD months/));
    await user.click(save);

    expect(update).toHaveBeenCalledWith({ settings: { plan_months: "ad" } });
    expect(refreshMe).toHaveBeenCalled();
  });

  it("tells staff who can't change the gym to ask the owner", () => {
    can.mockReturnValue(false);
    render(<PlanMonthsQuestion />);
    expect(screen.getByRole("status")).toHaveTextContent("the owner chooses");
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });
});
