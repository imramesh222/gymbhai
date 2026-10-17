import { t, type MessageKey } from "./i18n";

/** When an off-peak plan opens the door (PLAN.md §16.4, 9.4). 0 is Monday. */
export interface AccessWindow {
  days: number[];
  from: string;
  to: string;
}

const DAY_KEYS: MessageKey[] = [
  "days.mon",
  "days.tue",
  "days.wed",
  "days.thu",
  "days.fri",
  "days.sat",
  "days.sun",
];

export function dayName(day: number): string {
  return t(DAY_KEYS[day]);
}

/** [0,1,2,3,4] -> "Mon–Fri"; [5,6] -> "Sat, Sun"; all -> "Every day". */
export function describeDays(days: number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  if (sorted.length === 7) return t("days.every");
  const runs: number[][] = [];
  for (const day of sorted) {
    const run = runs[runs.length - 1];
    if (run && run[run.length - 1] === day - 1) run.push(day);
    else runs.push([day]);
  }
  return runs
    .map((run) =>
      run.length >= 3
        ? `${dayName(run[0])}–${dayName(run[run.length - 1])}`
        : run.map(dayName).join(", "),
    )
    .join(", ");
}

export function describeHours(hours: AccessWindow[] | null | undefined): string | null {
  if (!hours || hours.length === 0) return null;
  return hours.map((w) => `${describeDays(w.days)} ${w.from}–${w.to}`).join("; ");
}
