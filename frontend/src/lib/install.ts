"use client";

import { useSyncExternalStore } from "react";

import { isIos, isStandalone } from "@/lib/push";

/**
 * Installing the member app (PLAN.md §16.3, 8.5). Chrome on Android offers
 * `beforeinstallprompt` once, early: it is caught here as soon as this module
 * loads and kept until the member taps Install. iPhones have no such event:
 * they get instructions (Share → Add to Home Screen).
 */
interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let offer: InstallEvent | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // ours to show, at a good moment
    offer = event as InstallEvent;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    offer = null;
    changed();
  });
}

export type InstallWay = "prompt" | "ios" | null;

function way(): InstallWay {
  if (isStandalone()) return null;
  if (offer) return "prompt";
  return isIos() ? "ios" : null;
}

export function useInstall(): { way: InstallWay; install: () => Promise<boolean> } {
  const current = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    way,
    () => null,
  );
  return {
    way: current,
    install: async () => {
      if (!offer) return false;
      await offer.prompt();
      const { outcome } = await offer.userChoice;
      offer = null;
      changed();
      return outcome === "accepted";
    },
  };
}
