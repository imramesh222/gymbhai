/**
 * Scales for the charts in this folder. Colours are fixed here, validated
 * with the dataviz palette checks (light surface, white cards):
 * one series is brand-600; a second is orange; the heatmap is five steps of
 * the brand ramp, with grey for none.
 */

export const SERIES = ["#1d5fd1", "#eb6834"] as const;
export const HEAT = ["#97b6ff", "#648ffb", "#3a70ee", "#184eab", "#102f66"] as const;
export const HEAT_NONE = "#f1f5f9";
/** Gridlines and axes: one step off the surface, solid hairlines. */
export const GRID = "#e2e8f0";
export const AXIS_TEXT = "#64748b";

/**
 * Round tick values from 0 to at least `max`: 0, 5K, 10K, 15K. Whole numbers
 * only: everything charted here is a count, paisa or a percentage.
 */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = Math.max(
    1,
    [1, 2, 2.5, 5, 10].map((f) => f * power).find((s) => s >= rough)!,
  );
  const ticks: number[] = [];
  for (let value = 0; value < max + step * 0.999; value += step) {
    ticks.push(Math.round(value * 1e6) / 1e6);
  }
  return ticks;
}

const compactFormat = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** 950, 1.2K, 3.4L: short enough for an axis, in the way Nepal counts. */
export function compact(value: number): string {
  return compactFormat.format(value);
}

/** Money on an axis: Rs 6K, Rs 1.2L, from paisa. */
export function compactRupees(paisa: number): string {
  return `Rs ${compact(paisa / 100)}`;
}

/** Which bin of `bins` a value falls in, out of a maximum. 0 is its own. */
export function heatBin(value: number, max: number, bins = HEAT.length): number {
  if (value <= 0 || max <= 0) return -1;
  return Math.min(bins - 1, Math.floor((value / max) * bins - 1e-9));
}
