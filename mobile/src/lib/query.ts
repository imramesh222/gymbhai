/**
 * Loading and caching (TanStack Query), the cache kept on the phone
 * (PLAN.md §17.1): screens show the last data at once, offline too, and
 * re-read when the server says something changed (live.ts).
 *
 * Every key starts with the gym, so a member of two gyms keeps both, and
 * signing out of one forgets only that one.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { QueryCache, QueryClient } from "@tanstack/react-query";

import type { MemberLiveType } from "@shared/types";

import { ApiError, NetworkError } from "./api";
import { reportNetwork } from "./online";

const WEEK = 7 * 24 * 60 * 60 * 1000;

export const queryClient = new QueryClient({
  // No answer from the server is "offline" for the banner, whatever the
  // phone's Wi-Fi says; the next answer clears it.
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof NetworkError) reportNetwork(false);
    },
    onSuccess: () => reportNetwork(true),
  }),
  defaultOptions: {
    queries: {
      // Fresh until the server says otherwise (or the app comes back).
      staleTime: 60_000,
      // Kept for the persisted cache, so the QR survives a week offline.
      gcTime: 4 * WEEK,
      retry: (count, error) =>
        error instanceof NetworkError
          ? count < 2
          : !(error instanceof ApiError) && count < 1,
      // No signal: show what's saved and don't count it as an error yet.
      networkMode: "offlineFirst",
    },
    mutations: { networkMode: "always", retry: false },
  },
});

export const persister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key: "gymbhai.cache",
  throttleTime: 1000,
});

/** Bump when a cached shape changes, so an old cache is thrown away. */
export const CACHE_VERSION = "1";
export const CACHE_MAX_AGE = 4 * WEEK;

export const keys = {
  me: (slug: string) => [slug, "me"] as const,
  payments: (slug: string) => [slug, "payments"] as const,
  renew: (slug: string) => [slug, "renew"] as const,
  visits: (slug: string, month: string) => [slug, "visits", month] as const,
  notices: (slug: string) => [slug, "notices"] as const,
  freeze: (slug: string) => [slug, "freeze"] as const,
  classes: (slug: string, from: string) => [slug, "classes", from] as const,
  progress: (slug: string) => [slug, "progress"] as const,
  push: (slug: string) => [slug, "push"] as const,
};

/** What each live event means for the screens (§17.3). */
const AFFECTS: Record<Exclude<MemberLiveType, "resync">, string[]> = {
  member: ["me", "payments", "renew", "freeze", "visits", "classes"],
  payment_request: ["me", "payments", "renew"],
  freeze_request: ["me", "freeze"],
  check_in: ["me", "visits"],
  notice: ["me", "notices"],
  // Places taken at their branch, or a waitlist place given to them (§19.4).
  class: ["classes"],
};

/** Re-read what an event changed; everything after a resync. */
export function invalidateFor(slug: string, type: MemberLiveType | "everything") {
  if (type === "resync" || type === "everything") {
    void queryClient.invalidateQueries({ queryKey: [slug] });
    return;
  }
  for (const resource of AFFECTS[type] ?? []) {
    void queryClient.invalidateQueries({ queryKey: [slug, resource] });
  }
}

export function forgetGymData(slug: string) {
  queryClient.removeQueries({ queryKey: [slug] });
}
