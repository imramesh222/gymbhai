"use client";

/**
 * Live updates: a screen reloads when something it shows changes elsewhere —
 * a member scanning in at the door, an "I've paid" from the app, another desk
 * taking a payment (backend/app/services/live.py).
 *
 * One stream per app, opened by <LiveProvider>. Events carry ids only; a
 * screen that hears one reloads through the normal API. After a reconnect
 * events may have been missed, so every screen hears "resync" and reloads.
 */
import { createContext, useContext, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export type LiveType =
  | "check_in"
  | "payment_request"
  | "freeze_request"
  | "lead"
  | "expense"
  | "pt"
  | "class"
  | "member"
  | "message"
  | "shop"
  | "notice"
  | "staff";

export interface LiveEvent {
  type: LiveType | "resync";
  member?: string | null;
  branch?: string | null;
}

type Open = (signal: AbortSignal) => Promise<Response>;
type Listener = (event: LiveEvent) => void;

/** Calls `onEvent` with each event's `data:` once the blank line ends it. */
export async function readEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: LiveEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue; // a comment (": ping") or "retry:"
      try {
        onEvent(JSON.parse(data) as LiveEvent);
      } catch {
        // Not ours to understand; the next event will be.
      }
    }
  }
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });

/**
 * Keep a stream open until the returned function is called. The server ends
 * it every few minutes (the access token's lifetime); it reopens within a
 * second with a fresh token. A dropped connection is retried with backoff.
 */
export function subscribeLive(open: Open, onEvent: Listener): () => void {
  const controller = new AbortController();
  const { signal } = controller;
  void (async () => {
    let delay = 1000;
    let opened = false;
    while (!signal.aborted) {
      const started = Date.now();
      try {
        const response = await open(signal);
        if (opened) onEvent({ type: "resync" });
        opened = true;
        await readEvents(response.body!, onEvent);
      } catch (error) {
        if (signal.aborted) return;
        // Signed out, or not allowed: retrying won't change that.
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) return;
      }
      // A stream that lasted is a normal end (the token's lifetime): reopen
      // soon. One that keeps failing or closing at once backs off.
      delay = Date.now() - started > 60_000 ? 1000 : Math.min(delay * 2, 30_000);
      await wait(delay / 2, signal);
    }
  })();
  return () => controller.abort();
}

const LiveContext = createContext<Set<Listener> | null>(null);

/** Opens the stream while `open` is given (i.e. someone is signed in). */
export function LiveProvider({
  open,
  children,
}: {
  open: Open | null;
  children: React.ReactNode;
}) {
  const [listeners] = useState(() => new Set<Listener>());
  useEffect(() => {
    if (!open) return;
    return subscribeLive(open, (event) => listeners.forEach((l) => l(event)));
  }, [open, listeners]);
  return <LiveContext.Provider value={listeners}>{children}</LiveContext.Provider>;
}

/**
 * Run `onEvent` when one of `types` happens (and `match`, if given, agrees),
 * and on every resync. Bursts — a queue at the door at 6 a.m. — are batched:
 * at most one call per `everyMs`.
 */
export function useLive(
  types: LiveType[],
  onEvent: () => void,
  {
    match,
    everyMs = 1000,
  }: { match?: (event: LiveEvent) => boolean; everyMs?: number } = {},
): void {
  const listeners = useContext(LiveContext);
  const latest = useRef({ onEvent, match });
  useEffect(() => {
    latest.current = { onEvent, match };
  });
  const key = types.join(",");

  useEffect(() => {
    if (!listeners) return;
    const wanted = new Set(key.split(","));
    let timer: ReturnType<typeof setTimeout> | undefined;
    const listener: Listener = (event) => {
      if (event.type !== "resync") {
        if (!wanted.has(event.type)) return;
        if (latest.current.match && !latest.current.match(event)) return;
      }
      timer ??= setTimeout(() => {
        timer = undefined;
        latest.current.onEvent();
      }, everyMs);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
      clearTimeout(timer);
    };
  }, [listeners, key, everyMs]);
}
