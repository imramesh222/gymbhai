/**
 * When the newest notice this phone has opened Notices for was published, per
 * gym: the bell's dot (PLAN.md §17.5). Kept on the phone alone, so a second
 * phone shows the dot until Notices is opened there too.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useSyncExternalStore } from "react";

const storageKey = (slug: string) => `gymbhai.noticesSeen.${slug}`;

/** Missing while still reading the phone's copy; null when never opened. */
const seen = new Map<string, string | null>();
const reading = new Set<string>();
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function read(slug: string) {
  if (seen.has(slug) || reading.has(slug)) return;
  reading.add(slug);
  AsyncStorage.getItem(storageKey(slug))
    .catch(() => null)
    .then((value) => {
      reading.delete(slug);
      // Opening Notices while this was read already gave the newest.
      if (seen.has(slug)) return;
      seen.set(slug, value);
      emit();
    });
}

/** Undefined until known: no dot flashes on while the app starts. */
export function useNoticesSeen(slug: string): string | null | undefined {
  useEffect(() => read(slug), [slug]);
  return useSyncExternalStore(subscribe, () => seen.get(slug));
}

export function markNoticesSeen(slug: string, publishedAt: string) {
  const current = seen.get(slug);
  if (current && Date.parse(current) >= Date.parse(publishedAt)) return;
  seen.set(slug, publishedAt);
  emit();
  AsyncStorage.setItem(storageKey(slug), publishedAt).catch(() => {});
}

/** A notice newer than the last one this phone opened Notices for. */
export function hasUnread(
  latest: string | null | undefined,
  seenAt: string | null | undefined,
): boolean {
  if (!latest || seenAt === undefined) return false;
  return seenAt === null || Date.parse(latest) > Date.parse(seenAt);
}
