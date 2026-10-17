import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

import { TwoStepSetup } from "./TwoStepSetup";

const { setup, enable } = vi.hoisted(() => ({ setup: vi.fn(), enable: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  twoStepApi: { setup, enable },
}));

const CODES = Array.from({ length: 10 }, (_, i) => `code-000${i}`);

describe("setting up two-step sign-in", () => {
  beforeEach(() => {
    setup.mockReset().mockResolvedValue({
      secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
      uri: "otpauth://totp/GymBhai:sita?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    });
    enable.mockReset();
  });

  async function throughToTheCode() {
    const user = userEvent.setup();
    const onDone = vi.fn();
    render(<TwoStepSetup onDone={onDone} />);
    await user.type(screen.getByLabelText("Your password"), "correct-horse");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    return { user, onDone };
  }

  it("password, then the QR code, then the recovery codes", async () => {
    enable.mockResolvedValue({ recovery_codes: CODES });
    const { user, onDone } = await throughToTheCode();
    expect(setup).toHaveBeenCalledWith("correct-horse");
    expect(screen.getByTestId("two-step-secret")).toHaveTextContent(
      "JBSW Y3DP EHPK 3PXP",
    );
    expect(
      screen.getByRole("img", { name: "QR code for your authenticator app" }),
    ).toHaveAttribute("data-qr-value", expect.stringMatching(/^otpauth:\/\/totp\//));

    await user.type(screen.getByLabelText("6-digit code"), "654321");
    await user.click(screen.getByRole("button", { name: "Turn on" }));
    expect(enable).toHaveBeenCalledWith("654321");

    const list = screen.getByRole("list", { name: "Recovery codes" });
    expect(list.querySelectorAll("li")).toHaveLength(10);
    expect(onDone).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "I've saved them" }));
    expect(onDone).toHaveBeenCalled();
  });

  it("says when the first code is wrong", async () => {
    enable.mockRejectedValue(
      new ApiError(401, "bad_code", "That code is wrong or has expired."),
    );
    const { user } = await throughToTheCode();
    await user.type(screen.getByLabelText("6-digit code"), "000000");
    await user.click(screen.getByRole("button", { name: "Turn on" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That code is wrong or has expired.",
    );
  });
});
