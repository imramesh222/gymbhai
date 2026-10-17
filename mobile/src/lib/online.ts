/**
 * Is there internet? From the phone (expo-network), corrected by experience:
 * a request that got an answer means yes, whatever the phone thinks.
 */
import {
  addNetworkStateListener,
  getNetworkStateAsync,
  type NetworkState,
} from "expo-network";
import { useSyncExternalStore } from "react";

let online = true;
const listeners = new Set<() => void>();

function set(next: boolean) {
  if (next === online) return;
  online = next;
  listeners.forEach((listener) => listener());
}

function fromState(state: NetworkState): boolean {
  // isInternetReachable is null while the phone is still finding out.
  return state.isConnected !== false && state.isInternetReachable !== false;
}

let started = false;
export function startWatchingNetwork() {
  if (started) return;
  started = true;
  getNetworkStateAsync()
    .then((state) => set(fromState(state)))
    .catch(() => {});
  addNetworkStateListener((state) => set(fromState(state)));
}

export function isOnline(): boolean {
  return online;
}

/** A request that failed with no answer, or one that got through. */
export function reportNetwork(reachable: boolean) {
  set(reachable);
}

export function onOnlineChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Resolves when the internet comes back (at once if it's here). */
export function whenOnline(): Promise<void> {
  if (online) return Promise.resolve();
  return new Promise((resolve) => {
    const stop = onOnlineChange(() => {
      if (online) {
        stop();
        resolve();
      }
    });
  });
}

export function useOnline(): boolean {
  return useSyncExternalStore(onOnlineChange, isOnline, isOnline);
}
