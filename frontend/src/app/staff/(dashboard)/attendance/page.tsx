"use client";

import Link from "next/link";
import { useState } from "react";

import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/Card";
import { DateInput } from "@/components/ui/inputs";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t } from "@/i18n";
import { doorApi } from "@/lib/api";
import {
  addDays,
  daysBetween,
  formatDate,
  formatDateTime,
  todayInNepal,
} from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

const WEEKDAYS = [
  "attendance.sun",
  "attendance.mon",
  "attendance.tue",
  "attendance.wed",
  "attendance.thu",
  "attendance.fri",
  "attendance.sat",
] as const;
// The heatmap's hours: when gyms are open; a visit outside them is rare.
const HOURS = Array.from({ length: 18 }, (_, i) => i + 5);

function hourLabel(hour: number): string {
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}${hour < 12 ? "am" : "pm"}`;
}

/** Check-ins by day, when the gym is busy, and turned-away scans (§7, 7.9). */
export default function AttendancePage() {
  const { display } = useGymCalendar();
  const [from, setFrom] = useState(addDays(todayInNepal(), -6));
  const [to, setTo] = useState(todayInNepal());
  const summary = useLoad(() => doorApi.summary(from, to), [from, to]);
  const denied = useLoad(
    () =>
      doorApi.checkIns({ date_from: from, date_to: to, denied_only: true, limit: 50 }),
    [from, to],
  );
  useLive(
    ["check_in"],
    () => {
      summary.reload();
      denied.reload();
    },
    { everyMs: 3000 },
  );
  const s = summary.data;
  const days = Array.from({ length: Math.max(1, daysBetween(from, to) + 1) }, (_, i) =>
    addDays(from, i),
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("attendance.title")} />
      <div
        role="group"
        aria-label={t("attendance.range")}
        className="flex flex-wrap gap-2"
      >
        {[7, 30, 90].map((n) => {
          const active =
            from === addDays(todayInNepal(), -(n - 1)) && to === todayInNepal();
          return (
            <button
              key={n}
              type="button"
              aria-pressed={active}
              onClick={() => {
                setFrom(addDays(todayInNepal(), -(n - 1)));
                setTo(todayInNepal());
              }}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                active
                  ? "bg-brand-600 text-white shadow-brand"
                  : "bg-white text-slate-600 shadow-card ring-1 ring-hairline hover:bg-slate-50"
              }`}
            >
              {t("attendance.lastDays", { count: n })}
            </button>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <DateInput
          label={t("payments.from")}
          value={from}
          onChange={setFrom}
          display={display}
        />
        <DateInput
          label={t("payments.to")}
          value={to}
          onChange={setTo}
          display={display}
        />
      </div>
      {s && (
        <>
          <div className="grid grid-cols-3 gap-3">
            {[
              [s.let_in, t("attendance.visits")],
              [s.unique_members, t("attendance.members")],
              [s.denied, t("attendance.denied")],
            ].map(([value, label]) => (
              <Stat key={String(label)} value={value} label={String(label)} />
            ))}
          </div>
          <Card title={t("attendance.byDay")} className="min-w-0">
            <BarChart
              title={t("attendance.byDay")}
              labels={days.map((day) =>
                formatDate(day, display === "ad" ? "ad" : "bs").replace(/ \d{4}$/, ""),
              )}
              series={[
                {
                  key: "visits",
                  label: t("attendance.visits"),
                  values: days.map((day) => s.by_day[day] ?? 0),
                },
              ]}
            />
          </Card>
          <Card title={t("attendance.whenBusy")} className="min-w-0">
            <Heatmap
              title={t("attendance.whenBusy")}
              rows={WEEKDAYS.map((day) => t(day))}
              columns={HOURS.map(hourLabel)}
              values={s.by_weekday_hour.map((row) => HOURS.map((hour) => row[hour]))}
              format={(count) => t("attendance.visitsCount", { count })}
              everyNthColumn={3}
            />
          </Card>
        </>
      )}
      <Card title={t("attendance.deniedScans")}>
        {denied.data?.items.length === 0 && <EmptyState title={t("followUp.none")} />}
        <ul className="divide-y divide-hairline text-sm">
          {denied.data?.items.map((c) => (
            <li key={c.id} className="flex items-center justify-between py-2">
              <Link href={`/staff/members/${c.member_id}`} className="hover:underline">
                {c.member_name}{" "}
                <span className="text-slate-500">
                  · {formatDateTime(c.at, display)}
                </span>
              </Link>
              <StatusBadge status="expired" />
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
