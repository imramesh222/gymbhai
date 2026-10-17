"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { t } from "@/i18n";
import { doorApi } from "@/lib/api";
import {
  adMonths,
  bsMonths,
  addDays,
  daysInBsMonth,
  fromBs,
  toBs,
  todayInNepal,
  type Calendar,
} from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

interface Month {
  year: number;
  month: number;
}

function monthOf(iso: string, calendar: Calendar): Month {
  if (calendar === "bs") {
    const { year, month } = toBs(iso);
    return { year, month };
  }
  const [year, month] = iso.split("-").map(Number);
  return { year, month };
}

function bounds({ year, month }: Month, calendar: Calendar): [string, number] {
  if (calendar === "bs")
    return [fromBs({ year, month, day: 1 }), daysInBsMonth(year, month)];
  const first = `${year}-${String(month).padStart(2, "0")}-01`;
  return [first, new Date(Date.UTC(year, month, 0)).getUTCDate()];
}

function step({ year, month }: Month, by: number): Month {
  const index = year * 12 + (month - 1) + by;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

/**
 * A month of a member's visits (PLAN.md §7 member profile, §16.2 7.5), in the
 * gym's calendar: a filled day is a visit, a red ring a day they were turned
 * away. Each day says so to a screen reader too.
 */
export function VisitsCalendar({
  memberId,
  calendar,
}: {
  memberId: string;
  calendar: Calendar;
}) {
  const today = todayInNepal();
  const [shown, setShown] = useState<Month>(() => monthOf(today, calendar));
  const [first, length] = bounds(shown, calendar);
  const last = addDays(first, length - 1);
  const { data } = useLoad(
    () =>
      doorApi.checkIns({
        member_id: memberId,
        date_from: first,
        date_to: last,
        limit: 500,
      }),
    [memberId, first],
  );

  const days = new Map<string, { visited: boolean; denied: boolean }>();
  for (const row of data?.items ?? []) {
    const day = todayInNepal(new Date(row.at));
    const entry = days.get(day) ?? { visited: false, denied: false };
    if (row.result.startsWith("denied")) entry.denied = true;
    else if (row.result !== "duplicate") entry.visited = true;
    days.set(day, entry);
  }
  const visits = [...days.values()].filter((d) => d.visited).length;
  const turnedAway = [...days.values()].filter((d) => d.denied && !d.visited).length;
  const lead = new Date(`${first}T00:00:00Z`).getUTCDay();
  const names = calendar === "bs" ? bsMonths() : adMonths();
  const title = `${names[shown.month - 1]} ${shown.year}`;
  const atCurrent = monthOf(today, calendar);
  const isCurrent = atCurrent.year === shown.year && atCurrent.month === shown.month;

  return (
    <div>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setShown(step(shown, -1))}
          aria-label={t("visits.previous")}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
        >
          <ChevronLeft className="size-4" aria-hidden />
        </button>
        <p className="text-sm font-semibold text-slate-900">{title}</p>
        <button
          type="button"
          onClick={() => setShown(step(shown, 1))}
          disabled={isCurrent}
          aria-label={t("visits.next")}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
        >
          <ChevronRight className="size-4" aria-hidden />
        </button>
      </div>
      <div className="mt-2 grid grid-cols-7 gap-1 text-center text-[0.6875rem] font-semibold text-slate-500">
        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
          <span key={i} aria-hidden>
            {d}
          </span>
        ))}
      </div>
      <ol className="mt-1 grid grid-cols-7 gap-1" aria-label={title}>
        {Array.from({ length: lead }, (_, i) => (
          <li key={`lead-${i}`} aria-hidden />
        ))}
        {Array.from({ length }, (_, i) => {
          const iso = addDays(first, i);
          const day = days.get(iso);
          const label = day?.visited
            ? t("visits.dayVisited", { day: i + 1 })
            : day?.denied
              ? t("visits.dayTurnedAway", { day: i + 1 })
              : String(i + 1);
          return (
            <li
              key={iso}
              aria-label={label}
              className={`flex aspect-square items-center justify-center rounded-lg text-xs tabular-nums ${
                day?.visited
                  ? "bg-brand-600 font-semibold text-white"
                  : day?.denied
                    ? "font-semibold text-red-700 ring-2 ring-red-500 ring-inset"
                    : iso > today
                      ? "text-slate-300"
                      : "bg-slate-50 text-slate-600"
              } ${iso === today ? "outline-2 outline-offset-1 outline-slate-900" : ""}`}
            >
              {i + 1}
            </li>
          );
        })}
      </ol>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-3 rounded bg-brand-600" />
          {t("visits.count", { count: visits })}
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-3 rounded ring-2 ring-red-500 ring-inset" />
          {t("visits.turnedAway", { count: turnedAway })}
        </span>
      </p>
    </div>
  );
}
