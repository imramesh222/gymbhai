"use client";

import { useCallback, useRef, useState } from "react";

/**
 * One click is one request (PLAN.md §16.1, 6.5): while what a click started is
 * still running, more clicks (or Enter) do nothing. A double click on Send
 * would otherwise text the member twice; on Publish, every member twice.
 *
 * `run(action)` calls `action` unless one is running; if it returns a
 * promise, `busy` is true until it settles. The lock is a ref, so it holds
 * from the first click, before React has drawn the button disabled.
 */
export function useOnce() {
  const running = useRef(false);
  const [busy, setBusy] = useState(false);
  const run = useCallback((action: () => unknown) => {
    if (running.current) return;
    const result = action();
    if (!(result instanceof Promise)) return;
    running.current = true;
    setBusy(true);
    const done = () => {
      running.current = false;
      setBusy(false);
    };
    // An error still reaches the console, as it did before.
    void result.then(done, (error: unknown) => {
      done();
      throw error;
    });
  }, []);
  return { busy, run };
}
