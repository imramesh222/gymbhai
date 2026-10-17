import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

import ForgotPasswordPage from "./page";

const { requestPasswordReset, confirmPasswordReset, push } = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  confirmPasswordReset: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  authApi: { requestPasswordReset, confirmPasswordReset },
}));

describe("forgot password", () => {
  beforeEach(() => {
    requestPasswordReset.mockReset().mockResolvedValue({ expires_in: 600 });
    confirmPasswordReset.mockReset();
    push.mockReset();
  });

  async function askForCode() {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email or mobile number"), "9841000001");
    await user.click(screen.getByRole("button", { name: "Send me a code" }));
    return user;
  }

  it("asks for a code, then sets the new password", async () => {
    confirmPasswordReset.mockResolvedValue(undefined);
    const user = await askForCode();
    expect(requestPasswordReset).toHaveBeenCalledWith("9841000001");
    expect(
      screen.getByText(/If an account uses 9841000001, a code is on its way/),
    ).toHaveTextContent("10 minutes");

    await user.type(screen.getByLabelText("Code"), "24 68-10");
    await user.type(screen.getByLabelText("New password"), "a-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(confirmPasswordReset).toHaveBeenCalledWith(
      "9841000001",
      "246810",
      "a-new-password",
    );

    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(push).toHaveBeenCalledWith("/staff/login");
  });

  it("says when the code is wrong", async () => {
    confirmPasswordReset.mockRejectedValue(
      new ApiError(401, "bad_code", "That code is wrong or has expired."),
    );
    const user = await askForCode();
    await user.type(screen.getByLabelText("Code"), "000000");
    await user.type(screen.getByLabelText("New password"), "a-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That code is wrong or has expired.",
    );
  });
});
