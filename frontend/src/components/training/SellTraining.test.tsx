import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Branch, PtPlan } from "@/lib/api";
import { planEnd, todayInNepal } from "@/lib/dates";

import { SellTraining } from "./SellTraining";

const { plans, trainers, sell, can } = vi.hoisted(() => ({
  plans: vi.fn(),
  trainers: vi.fn(),
  sell: vi.fn(),
  can: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ptApi: { plans, trainers, sell },
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ can, me: { staff: { id: "owner" } } }),
}));
vi.mock("@/lib/gym", () => ({
  useGymCalendar: () => ({ calendar: "ad", display: "ad", date: (d: string) => d }),
}));

const MAIN: Branch = {
  id: "b1",
  name: "Baneshwor",
  address: null,
  phone: null,
  is_active: true,
};
const PACK: PtPlan = {
  id: "p1",
  name: "12 sessions",
  kind: "sessions",
  sessions: 12,
  duration_months: 2,
  duration_days: null,
  price: 12_000_00,
  is_active: true,
  sort_order: 0,
};

function open() {
  const onSold = vi.fn();
  render(
    <SellTraining
      memberId="m1"
      homeBranchId="b1"
      branches={[MAIN]}
      onClose={() => undefined}
      onSold={onSold}
    />,
  );
  return onSold;
}

describe("selling personal training", () => {
  beforeEach(() => {
    plans.mockReset().mockResolvedValue([PACK]);
    trainers.mockReset().mockResolvedValue([
      { id: "owner", name: "Sita Sharma" },
      { id: "t2", name: "Ram Thapa" },
    ]);
    sell.mockReset().mockResolvedValue({ package: { id: "pk1" }, payment: null });
    can.mockReset().mockReturnValue(true);
  });

  it("fills the price and end from the plan, and sends a part payment", async () => {
    const user = userEvent.setup();
    const onSold = open();
    const submit = await screen.findByRole("button", { name: "Sell personal training" });
    // The seller trains, so they start as the trainer; a plan is still needed.
    expect(screen.getByLabelText("Trainer")).toHaveValue("owner");
    expect(submit).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("PT plan"), "p1");
    expect(submit).toBeEnabled();
    expect(screen.getByLabelText("Price")).toHaveValue("12000");
    expect(screen.getByLabelText("Amount")).toHaveValue("12000");
    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "5000");
    expect(screen.getByText("Rs 7,000 will show as dues to collect later.")).toBeVisible();

    await user.click(submit);
    const today = todayInNepal();
    expect(sell).toHaveBeenCalledWith(
      "m1",
      {
        plan_id: "p1",
        trainer_id: "owner",
        branch_id: "b1",
        start_date: today,
        end_date: planEnd(today, PACK, "ad"),
        price: 12_000_00,
        discount: 0,
        payment: { amount: 5_000_00, method: "cash", transaction_ref: null },
      },
      expect.any(String),
    );
    expect(onSold).toHaveBeenCalledWith({ id: "pk1" });
  });

  it("takes no payment from staff who can't collect one", async () => {
    can.mockImplementation((permission: string) => permission !== "payments.collect");
    const user = userEvent.setup();
    open();
    await user.selectOptions(await screen.findByLabelText("PT plan"), "p1");
    expect(screen.queryByLabelText("Amount")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Sell personal training" }));
    expect(sell.mock.calls[0][1].payment).toBeNull();
  });

  it("says what's missing when there are no plans", async () => {
    plans.mockResolvedValue([]);
    open();
    expect(
      await screen.findByText("No PT plans yet: add them in Settings → Personal training."),
    ).toBeVisible();
  });
});
