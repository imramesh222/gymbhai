"use client";

import { useState } from "react";

import { t } from "@/i18n";

import { ChartFrame, Tooltip, useWidth, type Tip } from "./Frame";
import { AXIS_TEXT, HEAT, HEAT_NONE, heatBin } from "./scale";

const LEFT = 40;
const TOP = 4;
const BOTTOM = 22;
const GAP = 2;

/**
 * When the gym is busy: a grid of rows (days) by columns (hours), darker
 * where there were more visits. Grey is none. Each cell answers on hover;
 * the table has every value.
 */
export function Heatmap({
  title,
  rows,
  columns,
  values,
  format,
  everyNthColumn = 2,
}: {
  title: string;
  rows: string[];
  columns: string[];
  /** values[row][column] */
  values: number[][];
  format: (value: number) => string;
  everyNthColumn?: number;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const max = Math.max(0, ...values.flat());
  const cell = Math.max(10, Math.min(28, (width - LEFT) / columns.length));
  const height = TOP + rows.length * cell + BOTTOM;

  return (
    <ChartFrame
      title={title}
      legend={
        <div className="flex items-center gap-1.5 text-xs text-slate-600">
          <span>{t("chart.none")}</span>
          <span
            aria-hidden
            className="size-3 rounded-sm ring-1 ring-hairline"
            style={{ background: HEAT_NONE }}
          />
          <span className="ml-2">{t("chart.fewer")}</span>
          {HEAT.map((color) => (
            <span
              key={color}
              aria-hidden
              className="size-3 rounded-sm"
              style={{ background: color }}
            />
          ))}
          <span>{t("chart.more")}</span>
        </div>
      }
      table={{
        headers: ["", ...columns],
        rows: rows.map((row, r) => [row, ...values[r].map((v) => v)]),
      }}
    >
      <div
        ref={ref}
        className="relative overflow-x-auto"
        onPointerLeave={() => setTip(null)}
      >
        <svg
          width={LEFT + columns.length * cell}
          height={height}
          role="img"
          aria-label={title}
        >
          {rows.map((row, r) => (
            <g key={row}>
              <text
                x={LEFT - 8}
                y={TOP + r * cell + cell / 2}
                dy="0.32em"
                textAnchor="end"
                fontSize={11}
                fill={AXIS_TEXT}
              >
                {row}
              </text>
              {columns.map((column, c) => {
                const value = values[r][c];
                const bin = heatBin(value, max);
                return (
                  <rect
                    key={column}
                    x={LEFT + c * cell + GAP / 2}
                    y={TOP + r * cell + GAP / 2}
                    width={cell - GAP}
                    height={cell - GAP}
                    rx={3}
                    fill={bin < 0 ? HEAT_NONE : HEAT[bin]}
                    onPointerEnter={() =>
                      setTip({
                        x: LEFT + c * cell + cell / 2,
                        y: TOP + r * cell,
                        value: format(value),
                        label: `${row} ${column}`,
                      })
                    }
                  />
                );
              })}
            </g>
          ))}
          {columns.map((column, c) =>
            c % everyNthColumn === 0 ? (
              <text
                key={column}
                x={LEFT + c * cell + cell / 2}
                y={height - 6}
                textAnchor="middle"
                fontSize={11}
                fill={AXIS_TEXT}
              >
                {column}
              </text>
            ) : null,
          )}
        </svg>
        <Tooltip tip={tip} width={width} />
      </div>
    </ChartFrame>
  );
}
