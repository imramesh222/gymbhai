import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Lead } from "@/lib/api";

import { LeadDialog } from "./LeadDialog";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ can: () => true, me: { staff: { id: "owner" } } }),
}));
vi.mock("@/lib/gym", () => ({
  useGymCalendar: () => ({ calendar: "ad", display: "ad", date: (d: string) => d }),
}));

const ASKED: Lead = {
  id: "l1",
  branch_id: "b1",
  name: "Bikash Gurung",
  phone: "9812345678",
  email: null,
  source: "walk_in",
  plan_id: null,
  status: "new",
  follow_up_on: null,
  lost_reason: null,
  assigned_to: "owner",
  trial_on: null,
  referred_by_id: null,
  member_id: null,
  notes: "Asked about mornings",
  created_at: "2026-10-20T06:00:00Z",
  updated_at: "2026-10-20T06:00:00Z",
  plan_name: null,
  assigned_name: "Sita Sharma",
  referred_by_name: null,
};

describe("an enquiry's dialog", () => {
  it("stays open while the enquiry changes, its fields from the change", () => {
    const props = { onClose: () => undefined, onChanged: () => undefined };
    const { rerender } = render(<LeadDialog lead={ASKED} {...props} />);
    const dialog = screen.getByRole("dialog", { name: "Bikash Gurung" });
    expect(screen.getByLabelText("Notes")).toHaveValue("Asked about mornings");

    // A trial visit noted: the board reloads with the changed enquiry. The
    // same <dialog> stays open, so an Escape pressed meanwhile closes it.
    const trial: Lead = {
      ...ASKED,
      status: "trial",
      trial_on: "2026-10-20",
      notes: "Came at 7",
      updated_at: "2026-10-20T06:05:00Z",
    };
    rerender(<LeadDialog lead={trial} {...props} />);
    expect(screen.getByRole("dialog", { name: "Bikash Gurung" })).toBe(dialog);
    expect(dialog).toHaveAttribute("open");
    expect(screen.getByLabelText("Notes")).toHaveValue("Came at 7");
  });
});
