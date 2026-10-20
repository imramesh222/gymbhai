"use client";

import { useCallback, useEffect, useState } from "react";

import { staffPushApi, type NotificationKind, type StaffPushStatus } from "@/lib/api";
import {
  activated,
  isIos,
  isStandalone,
  keyBytes,
  supported,
  type PushState,
} from "@/lib/push";

/**
 * Notifications on a staff member's phone or computer (PLAN.md §18.6): what
 * members did that someone must answer. The same states as the member app's
 * (src/lib/push.ts), with the dashboard's own service worker, which keeps no
 * pages offline.
 *
 * A browser belongs to the sign-in that turned it on; the server stops
 * sending when that sign-in ends. Turning off tells the server and leaves the
 * browser's subscription alone: on a shared desk computer, a colleague may
 * have turned on the same browser for themselves.
 */

const SCOPE = "/staff";

/** Registered the first time someone turns them on, so maybe still installing. */
async function registration(): Promise<ServiceWorkerRegistration> {
  return activated(
    (await navigator.serviceWorker.getRegistration(SCOPE)) ??
      (await navigator.serviceWorker.register("/staff-sw.js", { scope: SCOPE })),
  );
}

async function subscription(): Promise<PushSubscription | null> {
  if (!supported()) return null;
  const reg = await navigator.serviceWorker.getRegistration(SCOPE);
  return (await reg?.pushManager.getSubscription()) ?? null;
}

function stateOf(status: StaffPushStatus, here: PushSubscription | null): PushState {
  if (!supported()) return isIos() && !isStandalone() ? "install" : "unsupported";
  if (!status.public_key) return "unavailable";
  if (Notification.permission === "denied") return "blocked";
  return here && status.on_here ? "on" : "off";
}

/**
 * Signed in again in a browser that had them on: the same person picks them
 * up without being asked; the server says no for anyone else. Never prompts,
 * never throws.
 */
export async function resumeStaffPush(): Promise<void> {
  try {
    if (!supported() || Notification.permission !== "granted") return;
    const here = await subscription();
    if (here) await staffPushApi.resume(here.endpoint);
  } catch {
    // My account can always turn them on again.
  }
}

export interface StaffPush {
  state: PushState;
  kinds: NotificationKind[];
  muted: NotificationKind[];
  error: string | null;
  on: () => Promise<void>;
  off: () => Promise<void>;
  choose: (muted: NotificationKind[]) => Promise<void>;
}

export function useStaffPush(): StaffPush {
  const [state, setState] = useState<PushState>("loading");
  const [status, setStatus] = useState<StaffPushStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const here = await subscription();
      const found = await staffPushApi.status(here?.endpoint);
      setStatus(found);
      setState(stateOf(found, here));
    } catch {
      setState("unsupported");
    }
  }, []);

  useEffect(() => {
    // Asked once the page is up: it talks to the browser and the server.
    void Promise.resolve().then(refresh);
  }, [refresh]);

  const on = useCallback(async () => {
    setError(null);
    if (!status?.public_key) return;
    try {
      // Asked only when someone taps "Turn on", never on load.
      if ((await Notification.requestPermission()) !== "granted") {
        setState("blocked");
        return;
      }
      const reg = await registration();
      const fresh =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(status.public_key),
        }));
      setStatus(await staffPushApi.on(fresh.toJSON()));
      setState("on");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [status]);

  const off = useCallback(async () => {
    setError(null);
    try {
      const here = await subscription();
      if (here) setStatus(await staffPushApi.off(here.endpoint));
      setState("off");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const choose = useCallback(
    async (muted: NotificationKind[]) => {
      setError(null);
      // The tick moves at once; the server's answer follows.
      setStatus((before) => (before ? { ...before, muted } : before));
      try {
        const here = await subscription();
        setStatus(await staffPushApi.choose(muted, here?.endpoint));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        void refresh();
      }
    },
    [refresh],
  );

  return {
    state,
    kinds: status?.kinds ?? [],
    muted: status?.muted ?? [],
    error,
    on,
    off,
    choose,
  };
}
