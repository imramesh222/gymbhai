/**
 * One tap is one action, however the network behaves (PLAN.md §17.4).
 *
 * 1. On screen: the first tap locks synchronously, in a ref. React state
 *    updates a frame later, so a `disabled={busy}` alone lets a fast second
 *    tap through. Later taps are ignored until the action ends.
 * 2. On the wire: the action gets an Idempotency-Key when it starts. No
 *    answer (no signal, a dropped connection) waits for the internet and
 *    sends again with the same key; so does tapping again after an error.
 *    A new key only after success, or when what is being sent changes.
 * 3. On the server: the same key returns the first answer and does nothing
 *    twice (backend/app/api/idempotency.py).
 *
 * Every button that changes something goes through this hook.
 */
import { randomUUID } from "expo-crypto";
import { useCallback, useEffect, useRef, useState } from "react";

import { NetworkError } from "./api";
import { errorMessage } from "./errors";
import { isOnline, reportNetwork, whenOnline } from "./online";

export interface Action<A extends unknown[]> {
  run: (...args: A) => void;
  /** Sending (or waiting to send). */
  busy: boolean;
  /** No internet: it will send by itself when it's back. */
  waiting: boolean;
  error: string | null;
  clearError: () => void;
}

/** Give up after this many tries with no answer, and say so. */
const MAX_ATTEMPTS = 6;
const RETRY_EVERY_MS = [1_000, 2_000, 5_000, 10_000, 15_000];
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function useAction<A extends unknown[], R>(
  action: (key: string, ...args: A) => Promise<R>,
  options: {
    onSuccess?: (result: R) => void;
    onError?: (error: unknown) => void;
    /** "run": no waiting for signal or resending; the action copes offline. */
    offline?: "wait" | "run";
  } = {},
): Action<A> {
  const locked = useRef(false);
  const key = useRef<{ value: string; args: string } | null>(null);
  const mounted = useRef(true);
  // The newest callbacks, for an action that finishes after a re-render.
  const latest = useRef({ action, options });
  useEffect(() => {
    latest.current = { action, options };
  });
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback((...args: A) => {
    if (locked.current) return;
    locked.current = true;
    // Same thing sent again (a retry after an error): the same key.
    const signature = safeSignature(args);
    if (!key.current || key.current.args !== signature) {
      key.current = { value: randomUUID(), args: signature };
    }
    const idempotencyKey = key.current.value;
    setBusy(true);
    setError(null);

    void (async () => {
      try {
        for (let attempt = 1; ; attempt++) {
          const waits = latest.current.options.offline !== "run";
          if (waits && !isOnline()) {
            if (mounted.current) setWaiting(true);
            // Until the phone says the internet is back; but try now and
            // then anyway, in case it was the server and not the phone.
            await Promise.race([
              whenOnline(),
              sleep(RETRY_EVERY_MS[attempt - 1] ?? 15_000),
            ]);
          }
          try {
            const result = await latest.current.action(idempotencyKey, ...args);
            reportNetwork(true);
            key.current = null;
            if (mounted.current) setWaiting(false);
            latest.current.options.onSuccess?.(result);
            return;
          } catch (caught) {
            if (waits && caught instanceof NetworkError && attempt < MAX_ATTEMPTS) {
              reportNetwork(false);
              if (mounted.current) setWaiting(true);
              continue;
            }
            throw caught;
          }
        }
      } catch (caught) {
        if (mounted.current) {
          setWaiting(false);
          setError(errorMessage(caught));
        }
        latest.current.options.onError?.(caught);
      } finally {
        locked.current = false;
        if (mounted.current) setBusy(false);
      }
    })();
  }, []);

  return { run, busy, waiting, error, clearError: () => setError(null) };
}

function safeSignature(args: unknown[]): string {
  try {
    return JSON.stringify(args);
  } catch {
    return String(Math.random());
  }
}
