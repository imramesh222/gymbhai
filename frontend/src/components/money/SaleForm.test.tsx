import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Member, Plan } from "@/lib/api";

import { emptySale, SaleForm, toSaleInput, type SaleDraft } from "./SaleForm";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  membersApi: { list },
}));

const BASE: Plan = {
  id: "one",
  name: "1 month",
  duration_months: 1,
  duration_days: null,
  price: 1_500_00,
  admission_fee: 500_00,
  all_branches: true,
  branch_ids: [],
  is_active: true,
  sort_order: 0,
  visit_limit: null,
  access_hours: null,
  seats: 1,
};
const COUPLE: Plan = {
  ...BASE,
  id: "couple",
  name: "Couple",
  price: 2_500_00,
  seats: 2,
};

function Harness({ onDraft }: { onDraft: (draft: SaleDraft) => void }) {
  const [draft, setDraft] = useState(() => emptySale("2026-10-20", ""));
  return (
    <SaleForm
      plans={[BASE, COUPLE]}
      branches={[]}
      value={draft}
      onChange={(next) => {
        setDraft(next);
        onDraft(next);
      }}
      calendar="ad"
      display="ad"
      firstMembership
      payer={{ id: "ram", name: "Ram Rai", phone: "9812000001" }}
    />
  );
}

describe("SaleForm, a family or couple plan (§19.1)", () => {
  it("asks who else is on it, and charges each newcomer the admission fee", async () => {
    list.mockResolvedValue({
      items: [
        { id: "ram", name: "Ram Rai", member_code: "FZ-1", status: "active" },
        { id: "sita", name: "Sita Rai", member_code: "FZ-2", status: "none" },
      ],
      total: 2,
    } as unknown as { items: Member[]; total: number });
    const onDraft = vi.fn();
    render(<Harness onDraft={onDraft} />);
    expect(screen.queryByText("Who else is on it?")).toBeNull();

    fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "couple" } });
    expect(screen.getByText("Who else is on it?")).toBeTruthy();
    expect(onDraft.mock.lastCall![0].admissionFee).toBe(500_00);

    fireEvent.change(screen.getByLabelText("Find a member"), {
      target: { value: "Sit" },
    });
    const sita = await screen.findByRole("button", { name: /Sita Rai/ });
    // Ram, who pays, is never offered as one of the others.
    expect(screen.queryByRole("button", { name: /Ram Rai/ })).toBeNull();
    fireEvent.click(sita);
    await waitFor(() =>
      expect(screen.getByText("Everyone this plan covers is on it.")).toBeTruthy(),
    );
    const draft = onDraft.mock.lastCall![0] as SaleDraft;
    expect(draft.admissionFee).toBe(2 * 500_00);
    expect(toSaleInput(draft).with_member_ids).toEqual(["sita"]);

    // A plan for one leaves nobody else on the sale.
    fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "one" } });
    expect(toSaleInput(onDraft.mock.lastCall![0]).with_member_ids).toEqual([]);
  });
});
