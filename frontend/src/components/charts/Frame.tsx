"use client";

import { useEffect, useRef, useState } from "react";

import { t } from "@/i18n";

/**
 * The chart's width in pixels, following its container. Charts draw in these
 * coordinates but size their <svg> at 100%, so a guess before the first
 * measurement can never push the page wider than the phone.
 */
export function useWidth<T extends HTMLElement>(fallback = 320) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(200, Math.round(entry.contentRect.width))),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

export interface Tip {
  x: number;
  y: number;
  /** The value: the strong line. */
  value: React.ReactNode;
  /** What it is: the quiet line, or one row per series. */
  rows?: { color?: string; label: string; value: React.ReactNode }[];
  label: string;
}

/** The hover/focus readout: value first, then what it is. */
export function Tooltip({ tip, width }: { tip: Tip | null; width: number }) {
  if (!tip) return null;
  const left = Math.min(Math.max(tip.x, 70), width - 70);
  return (
    <div
      role="presentation"
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs whitespace-nowrap text-white shadow-lifted"
      style={{ left, top: tip.y - 8 }}
    >
      {tip.rows ? (
        <>
          <p className="text-slate-300">{tip.label}</p>
          {tip.rows.map((row) => (
            <p key={row.label} className="flex items-center gap-1.5">
              {row.color && (
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-3 rounded"
                  style={{ background: row.color }}
                />
              )}
              <span className="font-semibold">{row.value}</span>
              <span className="text-slate-300">{row.label}</span>
            </p>
          ))}
        </>
      ) : (
        <>
          <p className="font-semibold">{tip.value}</p>
          <p className="text-slate-300">{tip.label}</p>
        </>
      )}
    </div>
  );
}

/**
 * Every chart's twin: the same numbers as a table, one tap away. Tooltips
 * help; this is what makes every value readable without them.
 */
export function ChartFrame({
  title,
  table,
  legend,
  children,
}: {
  title: string;
  table: { headers: string[]; rows: (string | number)[][] };
  legend?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure aria-label={title}>
      {legend && !asTable && <div className="mb-2">{legend}</div>}
      {asTable ? (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">{title}</caption>
            <thead className="text-left text-xs text-slate-500">
              <tr>
                {table.headers.map((header, index) => (
                  <th key={header} className={`py-1.5 ${index ? "text-right" : ""}`}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline tabular-nums">
              {table.rows.map((row) => (
                <tr key={String(row[0])}>
                  {row.map((cell, index) => (
                    <td key={index} className={`py-1.5 ${index ? "text-right" : ""}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
      <button
        type="button"
        onClick={() => setAsTable(!asTable)}
        className="mt-1 py-1 text-xs font-medium text-slate-500 hover:text-slate-800 print:hidden"
      >
        {asTable ? t("chart.showChart") : t("chart.showTable")}
      </button>
    </figure>
  );
}

/** A key for two or more series: a short mark in the series colour, then the name. */
export function Legend({
  items,
  shape = "rect",
}: {
  items: { label: string; color: string }[];
  shape?: "rect" | "line";
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className={shape === "rect" ? "size-2.5 rounded-sm" : "h-0.5 w-3.5 rounded"}
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
