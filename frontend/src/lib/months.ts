/**
 * Months of the gym's own calendar, as the API names them: "2083-06" for a
 * gym that shows BS, "2026-10" for one that shows AD (PLAN.md §10).
 */
import { adMonths, bsMonths } from "./dates";

/** `month` moved by `by` months. AD and BS both have twelve to a year. */
export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) + by;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** "Kartik", or "Kartik 2083" with the year. */
export function monthName(
  month: string,
  calendar: "ad" | "bs",
  withYear = false,
): string {
  const [year, number] = month.split("-").map(Number);
  const name = (calendar === "bs" ? bsMonths() : adMonths())[number - 1];
  return withYear ? `${name} ${year}` : name;
}
