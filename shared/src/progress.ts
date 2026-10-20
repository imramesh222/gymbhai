/**
 * Progress (PLAN.md §19.5): stored as whole numbers (grams, tenths of a
 * percent, millimetres), entered and shown in kg, % and cm.
 */
import type { MessageKey } from "./i18n";
import type { ProgressEntry } from "./types";

export type Measure =
  | "weight_g"
  | "body_fat"
  | "chest_mm"
  | "waist_mm"
  | "hips_mm"
  | "arm_mm"
  | "thigh_mm";

export const MEASURES: { key: Measure; label: MessageKey; unit: "kg" | "%" | "cm" }[] = [
  { key: "weight_g", label: "progress.weight", unit: "kg" },
  { key: "body_fat", label: "progress.bodyFat", unit: "%" },
  { key: "chest_mm", label: "progress.chest", unit: "cm" },
  { key: "waist_mm", label: "progress.waist", unit: "cm" },
  { key: "hips_mm", label: "progress.hips", unit: "cm" },
  { key: "arm_mm", label: "progress.arm", unit: "cm" },
  { key: "thigh_mm", label: "progress.thigh", unit: "cm" },
];

const PER_UNIT = { kg: 1000, "%": 10, cm: 10 } as const;

/** 62500 g → 62.5; 235 → 23.5; 760 mm → 76. One decimal at most. */
export function shown(stored: number | null, unit: "kg" | "%" | "cm"): number | null {
  if (stored === null) return null;
  return Math.round((stored / PER_UNIT[unit]) * 10) / 10;
}

/** What was typed ("62.5", "62,5") to the stored whole number; null if empty
 * or not a number. Weight is kept to the nearest 100 g. */
export function stored(text: string, unit: "kg" | "%" | "cm"): number | null {
  const value = Number(text.trim().replace(",", "."));
  if (!text.trim() || !Number.isFinite(value) || value <= 0) return null;
  return unit === "kg"
    ? Math.round(value * 10) * 100
    : Math.round(value * PER_UNIT[unit]);
}

/** Body mass index, one decimal; null without both. */
export function bmi(weightG: number | null, heightMm: number | null): number | null {
  if (!weightG || !heightMm) return null;
  const metres = heightMm / 1000;
  return Math.round((weightG / 1000 / (metres * metres)) * 10) / 10;
}

/** The latest value of a measure, and its change since the first and the last
 * check before it, oldest first in `entries` or not. */
export function changes(
  entries: ProgressEntry[],
  key: Measure,
): { latest: number; sinceFirst: number | null; sinceLast: number | null } | null {
  const having = entries
    .filter((e) => e[key] !== null)
    .sort((a, b) => a.measured_on.localeCompare(b.measured_on) || a.created_at.localeCompare(b.created_at));
  if (having.length === 0) return null;
  const latest = having[having.length - 1][key]!;
  return {
    latest,
    sinceFirst: having.length > 1 ? latest - having[0][key]! : null,
    sinceLast: having.length > 1 ? latest - having[having.length - 2][key]! : null,
  };
}
