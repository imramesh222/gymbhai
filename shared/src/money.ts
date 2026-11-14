/**
 * Money is integer paisa everywhere except on screen (CLAUDE.md). Shown with
 * Nepali grouping: Rs 1,00,000, not 100,000 (PLAN.md §10).
 */
import { getLocale, localDigits } from "./i18n";

const rupees = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function formatRs(paisa: number | null | undefined): string {
  if (paisa === null || paisa === undefined) return "—";
  const sign = paisa < 0 ? "−" : "";
  const symbol = getLocale() === "ne" ? "रु" : "Rs";
  return `${sign}${symbol} ${localDigits(rupees.format(Math.abs(paisa) / 100))}`;
}

/** To the nearest rupee: "Rs 1,833" a month, not "Rs 1,833.33". */
export function formatWholeRs(paisa: number): string {
  return formatRs(Math.round(paisa / 100) * 100);
}

/**
 * "1,500" or "1500.50" typed by a person -> paisa. Null if not a number.
 * A Nepali keyboard's "रु १५००" is the same amount.
 */
export function parseRs(input: string): number | null {
  const cleaned = input
    .replace(/[०-९]/g, (d) => String("०१२३४५६७८९".indexOf(d)))
    .replace(/[,\s]/g, "")
    .replace(/^(rs|रु)\.?/i, "");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, fraction = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

/** Paisa -> the plain number shown in an input box. */
export function toInput(paisa: number | null | undefined): string {
  if (paisa === null || paisa === undefined) return "";
  return paisa % 100 === 0 ? String(paisa / 100) : (paisa / 100).toFixed(2);
}
