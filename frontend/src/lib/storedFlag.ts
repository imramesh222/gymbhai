"use client";

import { useCallback, useSyncExternalStore } from "react";

const EVENT = "gb:stored-flag";

function read(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    // A private window or blocked storage: the default.
    return false;
  }
}

/**
 * An on/off preference kept on this device (a folded menu). The server and
 * the first render say "off"; then the device's choice. Never for anything
 * that must be kept: storage can be empty or blocked.
 */
export function useStoredFlag(key: string): [boolean, (on: boolean) => void] {
  const subscribe = useCallback(
    (changed: () => void) => {
      const onChange = (event: Event) => {
        if (!(event instanceof StorageEvent) || event.key === key) changed();
      };
      window.addEventListener("storage", onChange);
      window.addEventListener(EVENT, onChange);
      return () => {
        window.removeEventListener("storage", onChange);
        window.removeEventListener(EVENT, onChange);
      };
    },
    [key],
  );
  const value = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => false,
  );
  const set = useCallback(
    (on: boolean) => {
      try {
        localStorage.setItem(key, on ? "1" : "0");
      } catch {
        // Nowhere to keep it.
      }
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  return [value, set];
}
