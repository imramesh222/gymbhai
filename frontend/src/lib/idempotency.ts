/**
 * Keys that make a money request safe to send twice (PLAN.md §16.1,
 * backend/app/api/idempotency.py).
 *
 * A desk on weak mobile data taps Save, the answer is lost, they tap again.
 * The form keeps one key while it sends the same thing, so the second tap
 * gets the first answer back instead of making a second payment. It takes a
 * new key when what it sends changes, and once it has succeeded.
 */
import { useMemo, useRef } from "react";

/**
 * A random key. getRandomValues, unlike randomUUID, also works on plain-http
 * pages, such as a phone on the gym's Wi-Fi reaching a desk PC by its address.
 */
export function newIdempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export interface IdempotencyKeys {
  /** The key to send with `body`: the same one while `body` stays the same. */
  keyFor: (body: unknown) => string;
  /** The save went through: the next one is a new thing, with a new key. */
  succeeded: () => void;
}

export function useIdempotencyKey(): IdempotencyKeys {
  const last = useRef<{ body: string; key: string } | null>(null);
  return useMemo(
    () => ({
      keyFor(body) {
        const text = JSON.stringify(body);
        if (last.current?.body !== text) {
          last.current = { body: text, key: newIdempotencyKey() };
        }
        return last.current.key;
      },
      succeeded() {
        last.current = null;
      },
    }),
    [],
  );
}
