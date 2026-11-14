"use client";

import { useAuth } from "./auth";
import type { DateDisplay } from "./dates";
import { formatDate } from "./dates";

/** The signed-in gym's calendar choices, for forms and dates on screen. */
export function useGymCalendar() {
  const { me } = useAuth();
  const settings = me?.gym?.settings;
  const display: DateDisplay = settings?.date_display ?? "ad";
  return {
    /** How plan months are counted; null until the gym chooses (§5.1). */
    calendar: settings?.plan_months ?? null,
    display,
    date: (iso: string | null | undefined) => formatDate(iso, display),
    /** For tight spots, like a list row on a phone: one calendar, BS if both. */
    compactDate: (iso: string | null | undefined) =>
      formatDate(iso, display === "both" ? "bs" : display),
  };
}
