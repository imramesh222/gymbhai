"use client";

import { useState } from "react";

import { ChartFrame, Legend, Tooltip, useWidth } from "./Frame";
import { AXIS_TEXT, GRID, SERIES, compact, niceTicks } from "./scale";

export interface LineSeries {
  key: string;
  label: string;
  /** null where there is no value (before the gym existed). */
  values: (number | null)[];
}

const PAD = { top: 16, right: 48, bottom: 24, left: 44 };

/**
 * A trend over time: 2px lines, a light wash under a single series, the last
 * value labelled at its end. A crosshair snaps to the nearest point and the
 * readout lists every series there; arrow keys do the same from the keyboard.
 */
export function LineChart({
  title,
  labels,
  series,
  format = (value: number) => value.toLocaleString("en-IN"),
  tickFormat = compact,
  height = 200,
  max: fixedMax,
}: {
  title: string;
  labels: string[];
  series: LineSeries[];
  format?: (value: number) => string;
  /** The y-axis numbers: short, and in the value's own unit (rupees, not paisa). */
  tickFormat?: (value: number) => string;
  height?: number;
  /** A fixed top for the scale, e.g. 100 for percentages. */
  max?: number;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [at, setAt] = useState<number | null>(null);
  const values = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const ticks = niceTicks(fixedMax ?? Math.max(0, ...values));
  const top = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const x = (index: number) =>
    PAD.left + (labels.length < 2 ? plotW / 2 : (index / (labels.length - 1)) * plotW);
  const y = (value: number) => PAD.top + plotH - (value / top) * plotH;
  const step = Math.max(1, Math.ceil(labels.length / (plotW / 56)));

  function path(points: (number | null)[]): string {
    let d = "";
    let pen = false;
    points.forEach((value, index) => {
      if (value === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(index)},${y(value)}`;
      pen = true;
    });
    return d;
  }

  function lastIndex(points: (number | null)[]): number {
    for (let i = points.length - 1; i >= 0; i--) if (points[i] !== null) return i;
    return -1;
  }

  function nearest(clientX: number, box: DOMRect) {
    const relative = clientX - box.left - PAD.left;
    const index = Math.round((relative / plotW) * (labels.length - 1));
    setAt(Math.min(labels.length - 1, Math.max(0, index)));
  }

  return (
    <ChartFrame
      title={title}
      legend={
        series.length > 1 ? (
          <Legend
            shape="line"
            items={series.map((s, i) => ({ label: s.label, color: SERIES[i] }))}
          />
        ) : undefined
      }
      table={{
        headers: ["", ...series.map((s) => s.label)],
        rows: labels.map((label, index) => [
          label,
          ...series.map((s) => {
            const value = s.values[index];
            return value === null ? "—" : format(value);
          }),
        ]),
      }}
    >
      <div
        ref={ref}
        className="relative touch-pan-y"
        onPointerMove={(event) =>
          nearest(event.clientX, event.currentTarget.getBoundingClientRect())
        }
        onPointerLeave={() => setAt(null)}
      >
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={title}
          tabIndex={0}
          className="outline-none"
          onFocus={() => setAt(labels.length - 1)}
          onBlur={() => setAt(null)}
          onKeyDown={(event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            const move = event.key === "ArrowRight" ? 1 : -1;
            setAt((current) =>
              Math.min(labels.length - 1, Math.max(0, (current ?? 0) + move)),
            );
          }}
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
          {labels.map((label, index) =>
            // The last label always shows; one just before it would collide.
            index === labels.length - 1 ||
            (index % step === 0 && labels.length - 1 - index >= Math.ceil(step / 2)) ? (
              <text
                key={label}
                x={x(index)}
                y={height - 6}
                textAnchor="middle"
                fontSize={11}
                fill={AXIS_TEXT}
              >
                {label}
              </text>
            ) : null,
          )}
          {at !== null && (
            <line
              x1={x(at)}
              x2={x(at)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="#94a3b8"
              strokeWidth={1}
            />
          )}
          {series.map((s, si) => {
            const end = lastIndex(s.values);
            const line = path(s.values);
            return (
              <g key={s.key}>
                {series.length === 1 && end > 0 && (
                  <path
                    d={`${line}L${x(end)},${PAD.top + plotH}L${x(
                      s.values.findIndex((v) => v !== null),
                    )},${PAD.top + plotH}Z`}
                    fill={SERIES[si]}
                    opacity={0.1}
                  />
                )}
                <path
                  d={line}
                  fill="none"
                  stroke={SERIES[si]}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {end >= 0 && (
                  <>
                    <circle
                      cx={x(end)}
                      cy={y(s.values[end]!)}
                      r={4}
                      fill={SERIES[si]}
                      stroke="#ffffff"
                      strokeWidth={2}
                    />
                    {series.length === 1 && (
                      <text
                        x={x(end) + 8}
                        y={y(s.values[end]!)}
                        dy="0.32em"
                        fontSize={11}
                        fontWeight={600}
                        fill="#0f172a"
                      >
                        {format(s.values[end]!)}
                      </text>
                    )}
                  </>
                )}
                {at !== null && s.values[at] !== null && (
                  <circle
                    cx={x(at)}
                    cy={y(s.values[at]!)}
                    r={4}
                    fill={SERIES[si]}
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                )}
              </g>
            );
          })}
        </svg>
        <Tooltip
          width={width}
          tip={
            at === null
              ? null
              : {
                  x: x(at),
                  y: PAD.top + 8,
                  label: labels[at],
                  value: null,
                  rows: series.map((s, si) => ({
                    color: SERIES[si],
                    label: s.label,
                    value: s.values[at] === null ? "—" : format(s.values[at]!),
                  })),
                }
          }
        />
      </div>
    </ChartFrame>
  );
}
