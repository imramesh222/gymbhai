import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SignupPage from "./page";

const registerGym = vi.fn();
const push = vi.fn();

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ registerGym }) }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

async function fillTheForm() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Gym name"), "Fitness Zone");
  await user.type(screen.getByLabelText("Your name"), "Sita Sharma");
  await user.type(screen.getByLabelText("Mobile number"), "9841234567");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
  return user;
}

describe("gym sign-up", () => {
  beforeEach(() => {
    registerGym.mockReset();
    push.mockReset();
  });

  it("suggests an address from the gym's name", async () => {
    render(<SignupPage />);
    await fillTheForm();
    expect(screen.getByLabelText("Your gym's address")).toHaveValue("fitness-zone");
  });

  it("asks nothing about the calendar: that waits for the first sale", () => {
    render(<SignupPage />);
    expect(screen.queryByText(/BS months/)).not.toBeInTheDocument();
    expect(screen.queryByText(/AD months/)).not.toBeInTheDocument();
  });

  it("sends the form and goes to the dashboard", async () => {
    registerGym.mockResolvedValue({});
    render(<SignupPage />);
    const user = await fillTheForm();
    await user.click(screen.getByRole("checkbox", { name: /I accept the/ }));
    await user.click(screen.getByRole("button", { name: "Create my gym" }));

    expect(registerGym).toHaveBeenCalledWith(
      expect.objectContaining({
        slug: "fitness-zone",
        branch_name: "Main branch",
        owner_phone: "9841234567",
        accept_terms: true,
      }),
    );
    expect(push).toHaveBeenCalledWith("/staff");
  });

  it("needs the terms accepted", async () => {
    render(<SignupPage />);
    const user = await fillTheForm();
    await user.click(screen.getByRole("button", { name: "Create my gym" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Accept the terms of service and the privacy policy",
    );
    expect(registerGym).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "terms of service" })).toHaveAttribute(
      "href",
      "/terms",
    );
  });
});
