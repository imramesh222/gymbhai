import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";

function Harness({ type = "text" }: { type?: string }) {
  const [value, setValue] = useState("");
  return <Field label="Password" value={value} onChange={setValue} type={type} />;
}

describe("Field", () => {
  it("hides a password until the eye is pressed", async () => {
    const user = userEvent.setup();
    render(<Harness type="password" />);
    const input = screen.getByLabelText("Password");
    await user.type(input, "correct-horse");
    expect(input).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(input).toHaveAttribute("type", "text");
    // What they typed is untouched; only how it is drawn changed.
    expect(input).toHaveValue("correct-horse");

    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(input).toHaveAttribute("type", "password");
  });

  it("has no eye on ordinary fields", () => {
    render(<Harness />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
