"use client";

import { useCallback, useEffect, useState } from "react";

import { memberApi } from "@/lib/memberApi";

/**
 * Notifications on the member's phone (PLAN.md §16.3, 8.3).
 *
 * - unsupported: this browser can't take push.
 * - install: an iPhone, not opened from the Home Screen. iOS (16.4 and
 *   later) only gives push to an app added to the Home Screen.
 * - blocked: the member said no; only the browser's settings can undo that.
 * - unavailable: the server has no push key yet.
 * - off / on: on this phone.
 */
export type PushState =
  "loading" | "unsupported" | "install" | "blocked" | "unavailable" | "off" | "on";

export function isIos(): boolean {
  const ua = navigator.userAgent;
  // iPadOS says it's a Mac; a Mac has no touch screen.
  return (
    /iPhone|iPad|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  );
}

export function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function supported(): boolean {
  return (
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window
  );
}

async function registration(
  slug: string,
): Promise<ServiceWorkerRegistration | undefined> {
  return (
    (await navigator.serviceWorker.getRegistration(`/${slug}`)) ??
    (await navigator.serviceWorker.register("/sw.js", { scope: `/${slug}` }))
  );
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function check(slug: string): Promise<{ state: PushState; key: string | null }> {
  if (!supported()) {
    return { state: isIos() && !isStandalone() ? "install" : "unsupported", key: null };
  }
  const subscription = await (await registration(slug))?.pushManager.getSubscription();
  const status = await memberApi.pushStatus(subscription?.endpoint);
  if (!status.public_key) return { state: "unavailable", key: null };
  if (Notification.permission === "denied")
    return { state: "blocked", key: status.public_key };
  return {
    state: subscription && status.subscribed ? "on" : "off",
    key: status.public_key,
  };
}

/** Turn this phone off: on "Turn off", and before signing out. Never throws. */
export async function pushOff(slug: string): Promise<void> {
  try {
    if (!supported()) return;
    const subscription = await (
      await registration(slug)
    )?.pushManager.getSubscription();
    if (!subscription) return;
    await memberApi.pushOff(subscription.endpoint).catch(() => undefined);
    await subscription.unsubscribe();
  } catch {
    // Signing out must work whatever the browser does.
  }
}

export function usePush(slug: string) {
  const [state, setState] = useState<PushState>("loading");
  const [key, setKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const found = await check(slug);
      setState(found.state);
      setKey(found.key);
    } catch {
      setState("unsupported");
    }
  }, [slug]);

  useEffect(() => {
    // Asked once the page is up: it talks to the browser and the server.
    void Promise.resolve().then(refresh);
  }, [refresh]);

  const on = useCallback(async () => {
    setError(null);
    if (!key) return;
    try {
      // Asked only when the member taps "Turn on", never on load.
      if ((await Notification.requestPermission()) !== "granted") {
        setState("blocked");
        return;
      }
      const reg = await registration(slug);
      if (!reg) throw new Error("no service worker");
      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(key),
      });
      await memberApi.pushOn(subscription.toJSON());
      setState("on");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [key, slug]);

  const off = useCallback(async () => {
    await pushOff(slug);
    setState("off");
  }, [slug]);

  return { state, error, on, off };
}
