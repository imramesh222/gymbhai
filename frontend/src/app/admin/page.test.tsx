import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminGym, AdminSummary, SubscriptionPayment } from "@/lib/api";

import AdminGymsPage from "./page";

const { api } = vi.hoisted(() => ({
  api: {
    summary: vi.fn(),
    gyms: vi.fn(),
    payments: vi.fn(),
    plans: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
  },
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  adminApi: api,
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ can: () => true }) }));

const summary: AdminSummary = {
  mrr: 0,
  gyms: 1,
  by_state: { trial: 1, paying: 0, grace: 0, read_only: 0, suspended: 0 },
  trial_conversion: 0.5,
  trials_ended: 2,
  trials_converted: 1,
  lost_by_month: [{ month: "2026-06", gyms: 0 }],
  sms_sold_by_month: [{ month: "2026-06", credits: 500, amount: 500_00 }],
  going_quiet: 0,
};

const gym: AdminGym = {
  id: "g1",
  slug: "himalayan",
  name: "Himalayan Fitness",
  status: "active",
  owner_name: "Rajesh Shrestha",
  owner_phone: "9800000200",
  owner_email: null,
  owner_two_step: false,
  created_at: "2026-11-01T00:00:00Z",
  subscription_status: "trial",
  plan_name: "Free trial",
  ends_on: "2026-11-27",
  phase: "ok",
  active_members: 121,
  sms_balance: 50,
  pending_payments: 1,
  state: "trial",
  last_sign_in_at: null,
  check_ins_7d: 0,
  members_added_30d: 0,
  going_quiet: false,
  setup: {},
};

const payment: SubscriptionPayment = {
  id: "p1",
  gym_id: "g1",
  kind: "subscription",
  platform_plan_id: "plan1",
  months: 1,
  sms_credits: null,
  amount: 5000_00,
  transaction_ref: "ESW123",
  status: "pending",
  reject_reason: null,
  reviewed_at: null,
  created_at: "2026-11-14T06:00:00Z",
  gym_name: "Himalayan Fitness",
  plan_name: "Standard Plan",
};

describe("the admin's gyms page", () => {
  beforeEach(() => {
    api.summary.mockReset().mockResolvedValue(summary);
    api.gyms.mockReset().mockResolvedValue([gym]);
    api.payments.mockReset().mockResolvedValue([payment]);
    api.plans.mockReset().mockResolvedValue([]);
    api.reject.mockReset().mockResolvedValue(undefined);
  });

  it("names the months and puts the trial counts under the rate", async () => {
    render(<AdminGymsPage />);
    expect(await screen.findAllByText("Jun 2026")).toHaveLength(2);
    expect(screen.getByText("1 of 2 ended trials")).toBeInTheDocument();
    expect(
      screen.getByText("500 message credits", { exact: false }),
    ).toBeInTheDocument();
  });

  it("rejects a payment only with a reason the gym will see", async () => {
    const user = userEvent.setup();
    render(<AdminGymsPage />);
    const row = (await screen.findByText("ESW123", { exact: false })).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Reject" }));

    const dialog = screen.getByRole("dialog", { name: "Reject this payment" });
    const reject = within(dialog).getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();
    await user.type(
      within(dialog).getByLabelText("Reason the gym will see"),
      "  No such transaction  ",
    );
    await user.click(reject);

    expect(api.reject).toHaveBeenCalledWith("p1", "No such transaction");
    expect(
      await screen.findByText("Rejected. The gym has been told."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Reject this payment" }),
    ).not.toBeInTheDocument();
  });

  it("offers the same actions on the phone's card as in the table", async () => {
    render(<AdminGymsPage />);
    const menus = await screen.findAllByRole("combobox", { name: "Actions" });
    // One in the gym's card (phones), one in its table row (wider screens).
    expect(menus).toHaveLength(2);
    const options = menus.map((menu) =>
      within(menu)
        .getAllByRole("option")
        .map((option) => option.textContent),
    );
    expect(options[0]).toEqual(options[1]);
    expect(options[0][0]).toBe("Actions…");
    // No two-step to reset for an owner who never turned it on.
    expect(options[0]).not.toContain("Reset owner's two-step sign-in");
  });
});
