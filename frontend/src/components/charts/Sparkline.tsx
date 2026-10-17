/**
 * The trend inside a stat tile: quiet grey, the latest point in the brand
 * colour. Decoration for a number already written above it, so it is hidden
 * from screen readers and has no hover.
 */
export function Sparkline({
  values,
  width = 96,
  height = 28,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length < 2) return null;
  const max = Math.max(1, ...values);
  const x = (i: number) => 2 + (i / (values.length - 1)) * (width - 6);
  const y = (v: number) => height - 3 - (v / max) * (height - 6);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("");
  const last = values.length - 1;
  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <path
        d={d}
        fill="none"
        stroke="#cbd5e1"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={x(last)}
        cy={y(values[last])}
        r={3}
        fill="#1d5fd1"
        stroke="#ffffff"
        strokeWidth={2}
      />
    </svg>
  );
}
