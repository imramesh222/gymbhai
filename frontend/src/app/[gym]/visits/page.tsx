"use client";

import { t, type MessageKey } from "@/i18n";
import { adMonths, formatDate, todayInNepal } from "@/lib/dates";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

const WEEK: MessageKey[] = [
  "days.sun",
  "days.mon",
  "days.tue",
  "days.wed",
  "days.thu",
  "days.fri",
  "days.sat",
];

/** This month's visits as a calendar (§7), named and with its weekdays. */
export default function MemberVisits() {
  const { me } = useMember();
  const month = todayInNepal().slice(0, 7);
  const { data, reload } = useLoad(() => memberApi.visits(month), [month]);
  useLive(["check_in"], reload);
  if (!me) return null;
  const today = todayInNepal();
  const [year, number] = month.split("-").map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const firstWeekday = new Date(Date.UTC(year, number - 1, 1)).getUTCDay();
  const visited = new Set(
    (data ?? []).map((v) =>
      new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kathmandu" }).format(
        new Date(v.at),
      ),
    ),
  );
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("app.tab.visits")}</h1>
      <p className="text-3xl font-bold">
        {visited.size}{" "}
        <span className="text-base font-normal text-slate-600">
          {t("app.visits.thisMonth")}
        </span>
      </p>
      <div className="rounded-2xl bg-white p-3">
        <p className="mb-2 text-center text-sm font-semibold text-slate-900">
          {adMonths()[number - 1]} {year}
        </p>
        <div
          aria-hidden
          className="grid grid-cols-7 gap-1 text-center text-[0.6875rem] font-semibold text-slate-500"
        >
          {WEEK.map((key) => (
            <span key={key}>{t(key)}</span>
          ))}
        </div>
        <div className="mt-1 grid grid-cols-7 gap-1 text-center text-sm">
          {Array.from({ length: firstWeekday }, (_, i) => (
            <span key={`blank-${i}`} />
          ))}
          {Array.from({ length: days }, (_, i) => {
            const iso = `${month}-${String(i + 1).padStart(2, "0")}`;
            const here = visited.has(iso);
            return (
              <span
                key={iso}
                title={formatDate(iso, me.gym.date_display)}
                className={`rounded-full py-1.5 ${here ? "bg-emerald-500 font-semibold text-white" : "text-slate-600"} ${iso === today ? "ring-2 ring-emerald-500 ring-inset" : ""}`}
              >
                {i + 1}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
