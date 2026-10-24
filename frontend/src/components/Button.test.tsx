import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { Form } from "./Form";

/** A request that answers when the test says so. */
function pending() {
  let answer!: () => void;
  const promise = new Promise<void>((resolve) => (answer = resolve));
  return { promise, answer: () => act(async () => answer()) };
}

describe("one click is one request", () => {
  it("a double click on a button sends once, then it works again", async () => {
    const request = pending();
    const send = vi.fn(() => request.promise);
    render(<Button onClick={() => send()}>Send</Button>);
    const button = screen.getByRole("button", { name: "Send" });

    fireEvent.click(button);
    fireEvent.click(button);
    expect(send).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();

    await request.answer();
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("a button that does nothing slow is never disabled", () => {
    const open = vi.fn();
    render(<Button onClick={open}>Open</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(open).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Open" })).toBeEnabled();
  });

  it("a form submitted twice saves once, its button waiting meanwhile", async () => {
    const request = pending();
    const save = vi.fn(() => request.promise);
    render(
      <Form onSubmit={save}>
        <input aria-label="Name" />
        <Button type="submit">Save</Button>
        <Button>Cancel</Button>
      </Form>,
    );
    const submit = screen.getByRole("button", { name: "Save" });

    fireEvent.click(submit);
    fireEvent.submit(submit.closest("form")!);
    expect(save).toHaveBeenCalledTimes(1);
    expect(submit).toBeDisabled();
    // Only the submit button waits.
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();

    await request.answer();
    expect(submit).toBeEnabled();
  });

  it("a failed save can be tried again", async () => {
    const save = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(new Error("no signal")))
      .mockImplementationOnce(() => Promise.resolve());
    render(<Button onClick={() => save().catch(() => undefined)}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });

    await act(async () => fireEvent.click(button));
    expect(button).toBeEnabled();
    await act(async () => fireEvent.click(button));
    expect(save).toHaveBeenCalledTimes(2);
  });
});
