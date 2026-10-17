/**
 * The button every screen uses for actions (components/ui.tsx): pressed again
 * while sending, nothing happens; it says when it waits for signal.
 */
import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { ActionButton } from "@/components/ui";
import { NetworkError } from "@/lib/api";
import { reportNetwork } from "@/lib/online";
import { useAction } from "@/lib/useAction";

jest.mock("@/components/brand", () => ({ useBrand: () => "#1d5fd1" }));

function Paid({ send }: { send: (key: string) => Promise<unknown> }) {
  const action = useAction(send);
  return <ActionButton action={action} args={[]} label="I've paid" testID="paid" />;
}

beforeEach(() => reportNetwork(true));

test("pressed again while sending: one request, and the button says busy", async () => {
  let finish!: () => void;
  const send = jest.fn(() => new Promise<void>((resolve) => (finish = resolve)));
  await render(<Paid send={send} />);
  await fireEvent.press(screen.getByTestId("paid"));
  await fireEvent.press(screen.getByTestId("paid"));
  await fireEvent.press(screen.getByTestId("paid"));
  expect(send).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("paid")).toBeBusy();
  expect(screen.getByTestId("paid")).toBeDisabled();
  await act(async () => finish());
});

test("no signal: says it will send when the internet is back", async () => {
  const send = jest.fn(async () => {
    throw new NetworkError();
  });
  await render(<Paid send={send} />);
  await fireEvent.press(screen.getByTestId("paid"));
  await act(async () => {});
  expect(
    screen.getByText("No internet. It will send by itself when you're back online."),
  ).toBeTruthy();
});
