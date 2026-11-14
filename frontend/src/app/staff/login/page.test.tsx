import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type Me } from "@/lib/api";

import StaffLoginPage from "./page";

const { signIn, completeTwoStep, push } = vi.hoisted(() => ({
  signIn: vi.fn(),
  completeTwoStep: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: push }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth")>()),
  useAuth: () => ({ me: null, loading: false, signIn, completeTwoStep }),
}));

function me(overrides: Partial<Me["staff"]> = {}, required = false): Me {
  return {
    staff: {
      id: "s1",
      name: "Sita",
      email: null,
      phone: "9841000001",
      is_owner: true,
      is_platform_admin: false,
      is_super_admin: false,
      last_login_at: null,
      two_step_enabled: false,
      ...overrides,
    },
    gym: null,
    two_step_required: required,
    permissions: [],
    branch_ids: null,
    subscription: null,
    support_whatsapp: null,
    changelog_unread: false,
    language: "en",
    own_language: null,
    digits: "western",
  };
}

async function typePassword() {
  const user = userEvent.setup();
  render(<StaffLoginPage />);
  await user.type(screen.getByLabelText("Email or mobile number"), "9841000001");
  await user.type(screen.getByLabelText("Password"), "correct-horse");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("staff sign-in", () => {
  beforeEach(() => {
    signIn.mockReset();
    completeTwoStep.mockReset();
    push.mockReset();
  });

  it("goes straight in without two-step sign-in", async () => {
    signIn.mockResolvedValue({ me: me() });
    await typePassword();
    expect(push).toHaveBeenCalledWith("/staff");
  });

  it("asks for the code from the app when two-step sign-in is on", async () => {
    signIn.mockResolvedValue({ twoStepToken: "challenge" });
    completeTwoStep.mockResolvedValue(me({ two_step_enabled: true }));
    const user = await typePassword();

    await user.type(screen.getByLabelText("6-digit code"), "123 456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(completeTwoStep).toHaveBeenCalledWith("challenge", "123456");
    expect(push).toHaveBeenCalledWith("/staff");
  });

  it("takes a recovery code instead", async () => {
    signIn.mockResolvedValue({ twoStepToken: "challenge" });
    completeTwoStep.mockResolvedValue(me({ two_step_enabled: true }));
    const user = await typePassword();

    await user.click(screen.getByRole("button", { name: /Use a recovery code/ }));
    await user.type(screen.getByLabelText("Recovery code"), "abcd-efgh");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(completeTwoStep).toHaveBeenCalledWith("challenge", "abcd-efgh");
  });

  it("starts again from the password when the code step has expired", async () => {
    signIn.mockResolvedValue({ twoStepToken: "challenge" });
    completeTwoStep.mockRejectedValue(
      new ApiError(401, "two_step_expired", "Sign in again."),
    );
    const user = await typePassword();
    await user.type(screen.getByLabelText("6-digit code"), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That took too long");
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("sends an account that must set it up to the setup page", async () => {
    signIn.mockResolvedValue({ me: me({}, true) });
    await typePassword();
    expect(push).toHaveBeenCalledWith("/staff/two-step");
  });
});

describe("where sign-in lands", () => {
  it("goes back where they were going, on this site only", async () => {
    const { homeFor } = await import("@/lib/auth");
    expect(homeFor(me(), "/kiosk")).toBe("/kiosk");
    expect(homeFor(me(), "//evil.example")).toBe("/staff");
    expect(homeFor(me(), "https://evil.example")).toBe("/staff");
    expect(homeFor(me({ is_platform_admin: true }), "/kiosk")).toBe("/admin");
  });
});
