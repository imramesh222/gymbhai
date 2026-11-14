import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import type { GymReferral } from "@/lib/api";

import AdminReferralsPage from "./page";

const { api } = vi.hoisted(() => ({
  api: { referrals: vi.fn(), rewardReferral: vi.fn(), rejectReferral: vi.fn() },
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  adminApi: api,
}));

const referral: GymReferral = {
  id: "r1",
  referrer_gym_id: "g1",
  referrer_name: "Everest Gym",
  referred_gym_id: "g2",
  referred_name: "Pokhara Fitness",
  status: "ready",
  created_at: "2026-11-10T06:00:00Z",
  ready_at: "2026-11-12T06:00:00Z",
  note: null,
};

describe("the admin's gym referrals", () => {
  beforeEach(() => {
    api.referrals.mockReset().mockResolvedValue([referral]);
    api.rejectReferral.mockReset().mockResolvedValue(undefined);
  });

  it("rejects only with a note, and says who sees it", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <AdminReferralsPage />
      </ToastProvider>,
    );
    await user.click(await screen.findByRole("button", { name: "Reject" }));

    const dialog = screen.getByRole("dialog", { name: "Reject this referral" });
    expect(
      within(dialog).getByText("Everest Gym sent Pokhara Fitness"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Only admins see this. The gym that sent it sees “Not eligible”.",
      ),
    ).toBeInTheDocument();
    const reject = within(dialog).getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();
    await user.type(
      within(dialog).getByLabelText("Why, for our records"),
      " Same owner ",
    );
    await user.click(reject);

    expect(api.rejectReferral).toHaveBeenCalledWith("r1", "Same owner");
    expect(await screen.findByText("Rejected.")).toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Reject this referral" }),
    ).not.toBeInTheDocument();
  });
});
