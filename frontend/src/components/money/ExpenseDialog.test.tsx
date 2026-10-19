import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Branch, Expense } from "@/lib/api";
import { todayInNepal } from "@/lib/dates";

import { ExpenseDialog } from "./ExpenseDialog";

const MAIN: Branch = {
  id: "b1",
  name: "Baneshwor",
  address: null,
  phone: null,
  is_active: true,
};
const OTHER: Branch = { ...MAIN, id: "b2", name: "Koteshwor" };

const RENT: Expense = {
  id: "e1",
  branch_id: "b2",
  category: "rent",
  amount: 25_000_00,
  spent_on: "2026-09-01",
  method: "bank",
  paid_to: "Landlord",
  note: null,
  created_by: null,
  created_by_name: null,
  created_at: "2026-09-01T04:00:00Z",
  voided_at: null,
  void_reason: null,
};

function open(props: Partial<Parameters<typeof ExpenseDialog>[0]> = {}) {
  const onSave = vi.fn(() => Promise.resolve());
  render(
    <ExpenseDialog
      title="Add expense"
      branches={[MAIN]}
      wholeGym
      display="ad"
      onClose={() => undefined}
      onSave={onSave}
      {...props}
    />,
  );
  return onSave;
}

describe("ExpenseDialog", () => {
  it("sends paisa, today and the whole gym when there is one branch", async () => {
    const onSave = open();
    expect(screen.queryByLabelText("Branch")).toBeNull();
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: "electricity" },
    });
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "3,200" } });
    fireEvent.change(screen.getByLabelText(/Paid to/), {
      target: { value: "  NEA  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(
      {
        category: "electricity",
        amount: 3_200_00,
        spent_on: todayInNepal(),
        method: "cash",
        paid_to: "NEA",
        note: null,
        branch_id: null,
      },
      null,
    );
  });

  it("saves once however fast Save is tapped", async () => {
    let finish = () => undefined as void;
    const onSave = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    open({ onSave });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "rent" } });
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "100" } });
    const form = screen.getByRole("button", { name: "Save" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(onSave).toHaveBeenCalledTimes(1);
    finish();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled(),
    );
  });

  it("Same again: filled in from the last one, dated today", async () => {
    const onSave = open({ from: RENT, branches: [MAIN, OTHER] });
    expect(screen.getByLabelText("Branch")).toHaveValue("b2");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        category: "rent",
        amount: 25_000_00,
        method: "bank",
        paid_to: "Landlord",
        branch_id: "b2",
        spent_on: todayInNepal(),
      }),
      null,
    );
  });

  it("editing keeps the date and asks why", async () => {
    const onSave = open({ from: RENT, editing: true, branches: [MAIN, OTHER] });
    fireEvent.change(screen.getByLabelText(/Reason for the change/), {
      target: { value: "Wrong amount" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ spent_on: "2026-09-01" }),
      "Wrong amount",
    );
  });

  it("staff at some branches choose one of theirs, never the whole gym", () => {
    open({ wholeGym: false, branches: [MAIN, OTHER] });
    const branch = screen.getByLabelText("Branch");
    expect(branch).toHaveValue("b1");
    expect(screen.queryByRole("option", { name: "Whole gym" })).toBeNull();
  });
});
