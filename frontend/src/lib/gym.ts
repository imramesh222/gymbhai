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
    calendar: settings?.plan_months ?? "ad",
    display,
    date: (iso: string | null | undefined) => formatDate(iso, display),
  };
}
