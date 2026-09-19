/**
 * AD and BS dates (PLAN.md §5.1, §10), from the same BS table the backend
 * uses (bs-calendar.json, exported by backend/scripts/export_bs_calendar.py),
 * so a date never reads one way on screen and another on a receipt.
 *
 * Dates travel as ISO "YYYY-MM-DD" strings in AD. "Today" is today in Nepal.
 */
import table from "./bs-calendar.json";

export type DateDisplay = "ad" | "bs" | "both";
export type Calendar = "ad" | "bs";
export interface BsDate {
  year: number;
  month: number;
  day: number;
}

const years = table.years as unknown as Record<string, number[]>;
const [EPOCH_YEAR] = table.epoch.bs;
const EPOCH_AD = parseIso(table.epoch.ad);
const DAY = 86_400_000;

export const BS_MONTHS: string[] = table.months;
const AD_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function parseIso(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

function toIso(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function daysInBsMonth(year: number, month: number): number {
  const lengths = years[String(year)];
  if (!lengths) throw new RangeError(`BS year ${year} is outside the calendar`);
  return lengths[month - 1];
}

export function toBs(iso: string): BsDate {
  let days = Math.round((parseIso(iso) - EPOCH_AD) / DAY);
  if (days < 0) throw new RangeError("Date is before the BS calendar table");
  let year = EPOCH_YEAR;
  for (;;) {
    const lengths = years[String(year)];
    if (!lengths) throw new RangeError("Date is after the BS calendar table");
    const total = lengths.reduce((a, b) => a + b, 0);
    if (days < total) break;
    days -= total;
    year += 1;
  }
  let month = 1;
  while (days >= daysInBsMonth(year, month)) {
    days -= daysInBsMonth(year, month);
    month += 1;
  }
  return { year, month, day: days + 1 };
}

export function fromBs({ year, month, day }: BsDate): string {
  let days = 0;
  for (let y = EPOCH_YEAR; y < year; y++) {
    days += years[String(y)].reduce((a, b) => a + b, 0);
  }
  for (let m = 1; m < month; m++) days += daysInBsMonth(year, m);
  return toIso(EPOCH_AD + (days + day - 1) * DAY);
}

export function addDays(iso: string, days: number): string {
  return toIso(parseIso(iso) + days * DAY);
}

export function daysBetween(fromIso: string, toIsoDate: string): number {
  return Math.round((parseIso(toIsoDate) - parseIso(fromIso)) / DAY);
}

function shift(year: number, month: number, months: number): [number, number] {
  const index = year * 12 + (month - 1) + months;
  return [Math.floor(index / 12), (index % 12) + 1];
}

/** Same rule as backend/app/core/calendar.py: see its docstring. */
export function addMonths(iso: string, months: number, calendar: Calendar): string {
  if (calendar === "ad") {
    const [y, m, d] = iso.split("-").map(Number);
    const [year, month] = shift(y, m, months);
    const length = new Date(Date.UTC(year, month, 0)).getUTCDate();
    if (d <= length) return toIso(Date.UTC(year, month - 1, d));
    const [ny, nm] = shift(year, month, 1);
    return toIso(Date.UTC(ny, nm - 1, 1));
  }
  const bs = toBs(iso);
  const [year, month] = shift(bs.year, bs.month, months);
  if (bs.day <= daysInBsMonth(year, month)) return fromBs({ year, month, day: bs.day });
  const [ny, nm] = shift(year, month, 1);
  return fromBs({ year: ny, month: nm, day: 1 });
}

/** The last day (inclusive) of a plan starting on `start`. */
export function planEnd(
  start: string,
  plan: { duration_months: number | null; duration_days: number | null },
  calendar: Calendar,
): string {
  if (plan.duration_months)
    return addDays(addMonths(start, plan.duration_months, calendar), -1);
  return addDays(start, (plan.duration_days ?? 1) - 1);
}

export function formatBs(iso: string): string {
  const { year, month, day } = toBs(iso);
  return `${day} ${BS_MONTHS[month - 1]} ${year}`;
}

export function formatAd(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${AD_MONTHS[m - 1]} ${y}`;
}

/** A date the way the gym has chosen to show dates. */
export function formatDate(
  iso: string | null | undefined,
  display: DateDisplay,
): string {
  if (!iso) return "—";
  const day = iso.slice(0, 10);
  if (display === "ad") return formatAd(day);
  if (display === "bs") return formatBs(day);
  return `${formatBs(day)} (${formatAd(day)})`;
}

export function formatDateTime(iso: string, display: DateDisplay): string {
  const local = nepalParts(new Date(iso));
  return `${formatDate(local.date, display)}, ${local.time}`;
}

function nepalParts(date: Date): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kathmandu",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}

/** Today in Nepal (+05:45), whatever the device's own time zone. */
export function todayInNepal(now: Date = new Date()): string {
  return nepalParts(now).date;
}
