import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Stat } from "./Card";
import { ConfirmProvider, useConfirm } from "./ConfirmDialog";
import { DataTable } from "./DataTable";
import { Menu } from "./Menu";
import { Money } from "./Money";
import { Tabs } from "./Tabs";
import { ToastProvider, useToast } from "./Toast";

const { replace, push, params } = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  params: { value: new URLSearchParams() },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => "/staff/members/1",
  useSearchParams: () => params.value,
}));

describe("Toast", () => {
  afterEach(() => vi.useRealTimers());

  function Saver() {
    const toast = useToast();
    return (
      <button type="button" onClick={() => toast.success("Payment recorded")}>
        Save
      </button>
    );
  }

  it("confirms an action, then goes by itself", async () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Saver />
      </ToastProvider>,
    );
    act(() => screen.getByRole("button", { name: "Save" }).click());
    expect(screen.getByRole("status")).toHaveTextContent("Payment recorded");
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.queryByText("Payment recorded")).not.toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  function Eraser({ onAnswer }: { onAnswer: (yes: boolean) => void }) {
    const confirm = useConfirm();
    return (
      <button
        type="button"
        onClick={async () =>
          onAnswer(
            await confirm({
              title: "Extend everyone",
              message: "Adds 7 days to 214 memberships.",
              confirmLabel: "Extend",
              typeToConfirm: "214",
            }),
          )
        }
      >
        Open
      </button>
    );
  }

  it("needs the text typed before it agrees", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <ConfirmProvider>
        <Eraser onAnswer={onAnswer} />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByText("Adds 7 days to 214 memberships.")).toBeVisible();
    const extend = screen.getByRole("button", { name: "Extend" });
    expect(extend).toBeDisabled();
    await user.type(screen.getByLabelText("Type “214” to confirm"), "214");
    await user.click(extend);
    expect(onAnswer).toHaveBeenCalledWith(true);
  });

  it("answers no when cancelled", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <ConfirmProvider>
        <Eraser onAnswer={onAnswer} />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onAnswer).toHaveBeenCalledWith(false);
  });
});

describe("Menu", () => {
  it("opens, moves with the arrow keys and picks with Enter", async () => {
    const user = userEvent.setup();
    const freeze = vi.fn();
    const print = vi.fn();
    render(
      <Menu
        items={[
          { label: "Freeze", onSelect: freeze },
          { label: "Print card", onSelect: print },
          { label: "Hidden", onSelect: vi.fn(), hidden: true },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Freeze",
      "Print card",
    ]);
    await user.keyboard("{ArrowDown}{Enter}");
    expect(print).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("in a list row: an icon, still named for screen readers", async () => {
    const user = userEvent.setup();
    render(<Menu compact items={[{ label: "Edit", onSelect: vi.fn() }]} />);
    const button = screen.getByRole("button", { name: "More" });
    expect(button).toHaveTextContent("");
    await user.click(button);
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeVisible();
  });
});

describe("Tabs", () => {
  beforeEach(() => {
    replace.mockReset();
    params.value = new URLSearchParams();
  });

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "payments", label: "Payments", count: 3 },
  ];

  it("keeps the tab in the address", async () => {
    const user = userEvent.setup();
    render(
      <Tabs tabs={tabs} label="Member">
        panel
      </Tabs>,
    );
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.click(screen.getByRole("tab", { name: "Payments 3" }));
    expect(replace).toHaveBeenCalledWith("/staff/members/1?tab=payments", {
      scroll: false,
    });
  });

  it("opens on the tab in the address", () => {
    params.value = new URLSearchParams("tab=payments");
    render(
      <Tabs tabs={tabs} label="Member">
        panel
      </Tabs>,
    );
    expect(screen.getByRole("tab", { name: "Payments 3" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("DataTable", () => {
  const rows = [
    { id: "a", name: "Sita" },
    { id: "b", name: "Ram" },
  ];

  it("asks the page to sort, and selects rows", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const onChange = vi.fn();
    render(
      <DataTable
        caption="Members"
        columns={[{ key: "name", header: "Name", cell: (r) => r.name, sortable: true }]}
        rows={rows}
        rowKey={(r) => r.id}
        sort={{ key: "name", direction: "asc" }}
        onSortChange={onSortChange}
        selection={{ selected: new Set(["a"]), onChange }}
        mobile={(r) => r.name}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(onSortChange).toHaveBeenCalledWith({ key: "name", direction: "desc" });
    await user.click(screen.getAllByRole("checkbox", { name: "Select all" })[0]);
    expect(onChange).toHaveBeenCalledWith(new Set(["a", "b"]));
  });

  it("says so when there is nothing to show", () => {
    render(
      <DataTable
        caption="Members"
        columns={[{ key: "name", header: "Name", cell: () => null }]}
        rows={[]}
        rowKey={() => ""}
        mobile={() => null}
        empty={<p>No members yet</p>}
      />,
    );
    expect(screen.getByText("No members yet")).toBeVisible();
  });
});

describe("Stat", () => {
  it("keeps an amount on one line, its Rs set small", () => {
    render(<Stat value={<Money paisa={1_23_400_00} />} label="Owed" />);
    const amount = screen.getByText("1,23,400", { exact: false });
    expect(amount).toHaveClass("whitespace-nowrap");
    // Rs and the number are joined by a no-break space.
    expect(amount.textContent).toBe("Rs\u00a01,23,400");
    expect(screen.getByText("Rs")).toHaveClass("text-[0.6em]");
  });

  it("leaves other values and amounts elsewhere as they are", () => {
    render(
      <>
        <Stat value={63} label="Check-ins" />
        <Money paisa={500_00} />
      </>,
    );
    expect(screen.getByText("63")).toBeInTheDocument();
    expect(screen.getByText("Rs 500")).toBeInTheDocument();
  });
});
