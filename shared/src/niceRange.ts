/**
 * Round ticks spanning `min` to `max`, for a line whose scale doesn't start
 * at zero: body weight from 61.5 to 64 kg reads as 61, 62, 63, 64, not as a
 * flat line near the top of 0 to 70 (PLAN.md §19.5). Steps may be fractions
 * (0.5 kg). A line encodes position, not length, so this is honest for a
 * line; an area or a bar always starts at zero.
 */
export function niceRange(min: number, max: number, count = 4): number[] {
  let lo = min;
  let hi = max;
  if (!(hi > lo)) {
    // One value, or all the same: a little either side.
    const pad = Math.abs(lo) * 0.02 || 1;
    lo -= pad;
    hi += pad;
  }
  const rough = (hi - lo) / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * power).find((s) => s >= rough)!;
  const first = Math.floor(lo / step) * step;
  const ticks: number[] = [];
  for (let value = first; value < hi + step * 0.999; value += step) {
    ticks.push(Math.round(value * 1e6) / 1e6);
  }
  return ticks.length >= 2 ? ticks : [first, first + step];
}
