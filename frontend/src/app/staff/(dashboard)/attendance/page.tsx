"use client";

import Link from "next/link";
import { useState } from "react";

import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/Card";
import { DateInput } from "@/components/ui/inputs";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t } from "@/i18n";
import { doorApi } from "@/lib/api";
import { addDays, formatDate, formatDateTime, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Check-ins by day and hour, denied scans and busiest hours (§7). */
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
  const s = summary.data;
  const busiest = Math.max(1, ...Object.values(s?.by_hour ?? {}));
  const busiestDay = Math.max(1, ...Object.values(s?.by_day ?? {}));

  return (
    <div className="space-y-4">
      <PageHeader title={t("attendance.title")} />
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
          <Card title={t("attendance.byDay")}>
            <ul className="space-y-1 text-sm">
              {Object.entries(s.by_day).map(([day, count]) => (
                <li key={day} className="flex items-center gap-2">
                  <span className="w-44 shrink-0 text-slate-600">
                    {formatDate(day, display)}
                  </span>
                  <span
                    className="h-3 rounded bg-brand-600"
                    style={{ width: `${(count / busiestDay) * 100}%` }}
                  />
                  <span className="tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={t("attendance.byHour")}>
            <div className="flex h-32 items-end gap-1">
              {Array.from({ length: 24 }, (_, hour) => {
                const count = s.by_hour[String(hour)] ?? 0;
                return (
                  <div key={hour} className="flex flex-1 flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t bg-brand-600"
                      style={{ height: `${(count / busiest) * 100}%` }}
                      title={`${hour}:00 — ${count}`}
                    />
                    {hour % 3 === 0 && (
                      <span className="text-[10px] text-slate-500">{hour}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </>
      )}
      <Card title={t("attendance.deniedScans")}>
        {denied.data?.items.length === 0 && <EmptyState title={t("expiring.none")} />}
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
