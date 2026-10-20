import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Branch } from "@/lib/api";

import { AddReader } from "./AddReader";

const { addReader } = vi.hoisted(() => ({ addReader: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return { ...real, doorApi: { ...real.doorApi, addReader } };
});

const MAIN: Branch = {
  id: "b1",
  name: "Baneshwor",
  address: null,
  phone: null,
  is_active: true,
};

describe("adding a fingerprint or face reader", () => {
  beforeEach(() => {
    addReader.mockReset().mockResolvedValue({ device: {}, token: "TOKEN-ONCE-123" });
  });

  it("knows a ZKTeco reader by its serial, and says how to point it here", async () => {
    const user = userEvent.setup();
    const onAdded = vi.fn();
    render(<AddReader branches={[MAIN]} onClose={() => undefined} onAdded={onAdded} />);
    expect(screen.getByLabelText("Serial number")).toBeRequired();
    await user.type(screen.getByLabelText("Name"), "Front door");
    await user.type(screen.getByLabelText("Serial number"), "CQZ7224160142");
    await user.click(
      screen.getByRole("button", { name: "Add a fingerprint or face reader" }),
    );
    expect(addReader).toHaveBeenCalledWith({
      kind: "zkteco",
      name: "Front door",
      branch_id: "b1",
      serial: "CQZ7224160142",
    });
    expect(onAdded).toHaveBeenCalled();
    expect(screen.getByText(/Cloud Server Setting \(ADMS\)/)).toBeVisible();
  });

  it("opened before the branches have loaded, still sends the branch", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <AddReader branches={[]} onClose={() => undefined} onAdded={() => undefined} />,
    );
    const add = screen.getByRole("button", {
      name: "Add a fingerprint or face reader",
    });
    expect(add).toBeDisabled();
    rerender(
      <AddReader
        branches={[MAIN]}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    await user.type(screen.getByLabelText("Name"), "Front door");
    await user.type(screen.getByLabelText("Serial number"), "CQZ7224160142");
    await user.click(add);
    expect(addReader.mock.calls[0][0]).toMatchObject({ branch_id: "b1" });
  });

  it("gives a Hikvision reader's bridge its settings, token and all", async () => {
    const user = userEvent.setup();
    render(
      <AddReader
        branches={[MAIN]}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    await user.selectOptions(screen.getByLabelText("Brand"), "hikvision");
    expect(screen.getByLabelText(/Serial number/)).not.toBeRequired();
    await user.type(screen.getByLabelText("Name"), "Side door");
    await user.click(
      screen.getByRole("button", { name: "Add a fingerprint or face reader" }),
    );
    expect(addReader.mock.calls[0][0]).toMatchObject({
      kind: "hikvision",
      serial: null,
    });
    const config = screen.getByLabelText("The bridge's settings");
    expect(config).toHaveTextContent('"token": "TOKEN-ONCE-123"');
    expect(screen.getByText(/shown only once/)).toBeVisible();
  });
});
