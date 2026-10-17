"use client";

import { useState } from "react";

import { ChartFrame, Legend, Tooltip, useWidth, type Tip } from "./Frame";
import { AXIS_TEXT, GRID, SERIES, compact, niceTicks } from "./scale";

export interface BarSeries {
  key: string;
  label: string;
  values: number[];
}

const PAD = { top: 20, right: 8, bottom: 24, left: 44 };
const MAX_BAR = 24;
const GAP = 2;

/** A column with its data end rounded and its foot square on the baseline. */
function column(x: number, y: number, width: number, height: number): string {
  const r = Math.min(4, width / 2, height);
  return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${
    x + width
  },${y} ${x + width},${y + r}V${y + height}Z`;
}

/**
 * Columns for magnitude over categories (hours, months): one series in the
 * brand colour, or two side by side with a legend. Each column is its own
 * hover and focus target; the tallest is labelled; the table has the rest.
 */
export function BarChart({
  title,
  labels,
  series,
  format = (value: number) => value.toLocaleString("en-IN"),
  tickFormat = compact,
  height = 180,
  everyNthLabel,
}: {
  title: string;
  labels: string[];
  series: BarSeries[];
  format?: (value: number) => string;
  /** The y-axis numbers: short, and in the value's own unit (rupees, not paisa). */
  tickFormat?: (value: number) => string;
  height?: number;
  /** Show every nth x label when they would crowd (24 hours on a phone). */
  everyNthLabel?: number;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const max = Math.max(0, ...series.flatMap((s) => s.values));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const band = plotW / Math.max(1, labels.length);
  const barW = Math.max(
    2,
    Math.min(MAX_BAR, (band * 0.7 - GAP * (series.length - 1)) / series.length),
  );
  const groupW = barW * series.length + GAP * (series.length - 1);
  const y = (value: number) => PAD.top + plotH - (value / top) * plotH;
  const step = everyNthLabel ?? Math.max(1, Math.ceil(labels.length / (plotW / 44)));
  let peak = { series: -1, index: -1 };
  series.forEach((s, si) =>
    s.values.forEach((value, index) => {
      if (value > 0 && value === max && peak.index < 0) peak = { series: si, index };
    }),
  );

  const show = (si: number, index: number, x: number) =>
    setTip({
      x: x + barW / 2,
      y: y(series[si].values[index]),
      value: format(series[si].values[index]),
      label:
        series.length > 1 ? `${labels[index]} · ${series[si].label}` : labels[index],
    });

  return (
    <ChartFrame
      title={title}
      legend={
        series.length > 1 ? (
          <Legend
            items={series.map((s, i) => ({ label: s.label, color: SERIES[i] }))}
          />
        ) : undefined
      }
      table={{
        headers: ["", ...series.map((s) => s.label)],
        rows: labels.map((label, index) => [
          label,
          ...series.map((s) => format(s.values[index])),
        ]),
      }}
    >
      <div ref={ref} className="relative" onPointerLeave={() => setTip(null)}>
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={title}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke={GRID}
                strokeWidth={1}
              />
              <text
                x={PAD.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                fontSize={11}
                fill={AXIS_TEXT}
                className="tabular-nums"
              >
                {tickFormat(tick)}
              </text>
            </g>
          ))}
          {labels.map((label, index) => {
            const x0 = PAD.left + index * band + (band - groupW) / 2;
            return (
              <g key={label}>
                {series.map((s, si) => {
                  const value = s.values[index];
                  const x = x0 + si * (barW + GAP);
                  const h = Math.max(0, PAD.top + plotH - y(value));
                  return (
                    <g key={s.key}>
                      {h > 0 && (
                        <path d={column(x, y(value), barW, h)} fill={SERIES[si]} />
                      )}
                      {/* The hit target: the whole band, not just the paint. */}
                      <rect
                        x={PAD.left + index * band + (si * band) / series.length}
                        y={PAD.top}
                        width={band / series.length}
                        height={plotH}
                        fill="transparent"
                        tabIndex={0}
                        role="img"
                        aria-label={`${label}${series.length > 1 ? ` ${s.label}` : ""}: ${format(value)}`}
                        onPointerEnter={() => show(si, index, x)}
                        onFocus={() => show(si, index, x)}
                        onBlur={() => setTip(null)}
                        className="outline-none focus:fill-slate-900/5"
                      />
                      {peak.series === si && peak.index === index && (
                        <text
                          x={x + barW / 2}
                          y={y(value) - 6}
                          textAnchor="middle"
                          fontSize={11}
                          fontWeight={600}
                          fill="#0f172a"
                        >
                          {format(value)}
                        </text>
                      )}
                    </g>
                  );
                })}
                {index % step === 0 && (
                  <text
                    x={PAD.left + index * band + band / 2}
                    y={height - 6}
                    textAnchor="middle"
                    fontSize={11}
                    fill={AXIS_TEXT}
                  >
                    {label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        <Tooltip tip={tip} width={width} />
      </div>
    </ChartFrame>
  );
}
