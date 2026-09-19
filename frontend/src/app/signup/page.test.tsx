import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SignupPage from "./page";

const registerGym = vi.fn();
const push = vi.fn();

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ registerGym }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

async function fillEverythingButTheCalendar() {
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
    await fillEverythingButTheCalendar();
    expect(screen.getByLabelText("Your gym's address")).toHaveValue("fitness-zone");
  });

  it("does not pre-select a calendar", () => {
    render(<SignupPage />);
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
    }
  });

  it("refuses to submit until both calendar choices are made", async () => {
    render(<SignupPage />);
    await fillEverythingButTheCalendar();
    // Straight to the submit handler, past the browser's own required check.
    fireEvent.submit(screen.getByRole("button", { name: "Create my gym" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose how plan months are counted",
    );
    expect(registerGym).not.toHaveBeenCalled();
  });

  it("sends the choices and goes to the dashboard", async () => {
    registerGym.mockResolvedValue({});
    render(<SignupPage />);
    const user = await fillEverythingButTheCalendar();
    await user.click(screen.getByLabelText(/BS months/));
    await user.click(screen.getByLabelText("Both"));
    await user.click(screen.getByRole("button", { name: "Create my gym" }));

    expect(registerGym).toHaveBeenCalledWith(
      expect.objectContaining({
        slug: "fitness-zone",
        plan_months: "bs",
        date_display: "both",
        branch_name: "Main branch",
        owner_phone: "9841234567",
      }),
    );
    expect(push).toHaveBeenCalledWith("/staff");
  });
});
