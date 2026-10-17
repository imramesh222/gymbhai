/**
 * One tap is one action (PLAN.md §17.4): taps 10 ms apart send one request;
 * no answer sends again with the same key; success makes a new one.
 */
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { Pressable, Text } from "react-native";

import { NetworkError } from "@/lib/api";
import { reportNetwork } from "@/lib/online";
import { useAction } from "@/lib/useAction";

function Pay({
  send,
  expose,
}: {
  send: (key: string, amount: number) => Promise<string>;
  expose?: (run: (amount: number) => void) => void;
}) {
  const action = useAction(send);
  expose?.(action.run);
  return (
    <>
      <Pressable testID="pay" onPress={() => action.run(1500)}>
        <Text>{action.busy ? "busy" : "idle"}</Text>
      </Pressable>
      {action.waiting ? <Text>waiting</Text> : null}
      {action.error ? <Text>{action.error}</Text> : null}
    </>
  );
}

const flush = () => act(async () => {});

beforeEach(() => {
  jest.useRealTimers();
  reportNetwork(true);
});

test("a double tap sends one request", async () => {
  let resolve!: (value: string) => void;
  const send = jest.fn(() => new Promise<string>((r) => (resolve = r)));
  let tap!: (amount: number) => void;
  await render(<Pay send={send} expose={(run) => (tap = run)} />);
  // Two taps in the same frame, before React re-renders (so `busy` is still
  // false on screen), then a third 10 ms later.
  await act(async () => {
    tap(1500);
    tap(1500);
    await new Promise((r) => setTimeout(r, 10));
    tap(1500);
  });
  expect(send).toHaveBeenCalledTimes(1);
  await act(async () => {
    resolve("ok");
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(screen.getByText("idle")).toBeTruthy();
});

test("no answer sends again with the same key; success makes a new key", async () => {
  jest.useFakeTimers();
  const keys: string[] = [];
  let failures = 1;
  const send = jest.fn(async (key: string) => {
    keys.push(key);
    if (failures-- > 0) throw new NetworkError();
    return "ok";
  });
  await render(<Pay send={send} />);
  await fireEvent.press(screen.getByTestId("pay"));
  await flush();
  expect(screen.getByText("waiting")).toBeTruthy();
  // The first retry after no answer: within two seconds.
  await act(async () => {
    await jest.advanceTimersByTimeAsync(2_000);
  });
  await flush();
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);

  await fireEvent.press(screen.getByTestId("pay"));
  await flush();
  expect(keys).toHaveLength(3);
  expect(keys[2]).not.toBe(keys[0]);
});

test("tapping again after an error sends the same key", async () => {
  const keys: string[] = [];
  const send = jest.fn(async (key: string) => {
    keys.push(key);
    throw new Error("refused");
  });
  await render(<Pay send={send} />);
  await fireEvent.press(screen.getByTestId("pay"));
  await flush();
  await fireEvent.press(screen.getByTestId("pay"));
  await flush();
  expect(keys).toEqual([keys[0], keys[0]]);
});

test("with no internet it waits, then sends by itself", async () => {
  reportNetwork(false);
  const send = jest.fn(async () => "ok");
  await render(<Pay send={send} />);
  await fireEvent.press(screen.getByTestId("pay"));
  await flush();
  expect(send).not.toHaveBeenCalled();
  expect(screen.getByText("waiting")).toBeTruthy();
  await act(async () => reportNetwork(true));
  await flush();
  expect(send).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("waiting")).toBeNull();
});

test('offline: "run" sends at once and never resends', async () => {
  reportNetwork(false);
  const send = jest.fn(async () => {
    throw new NetworkError();
  });
  function Reopen() {
    const action = useAction(send, { offline: "run" });
    return (
      <Pressable testID="go" onPress={() => action.run()}>
        <Text>{action.error ?? "fine"}</Text>
      </Pressable>
    );
  }
  await render(<Reopen />);
  await fireEvent.press(screen.getByTestId("go"));
  await flush();
  expect(send).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("fine")).toBeNull();
});
