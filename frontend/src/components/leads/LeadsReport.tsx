"use client";

import Link from "next/link";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { DateInput } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import { leadsApi, type SourceRow } from "@/lib/api";
import { addDays, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

function percent(row: SourceRow): string {
  return row.conversion === null ? "—" : `${Math.round(row.conversion * 100)}%`;
}

/** Where enquiries come from, and which turn into members (9.1, 9.6). */
export function LeadsReport() {
  const { display } = useGymCalendar();
  const [to, setTo] = useState(todayInNepal());
  const [from, setFrom] = useState(addDays(todayInNepal(), -29));
  const { data } = useLoad(() => leadsApi.report(from, to), [from, to]);
  return (
    <div className="space-y-4">
      <div className="grid max-w-md grid-cols-2 gap-3">
        <DateInput
          label={t("leads.from")}
          value={from}
          onChange={setFrom}
          display={display}
        />
        <DateInput
          label={t("leads.to")}
          value={to}
          onChange={setTo}
          display={display}
        />
      </div>
      {data && (
        <Card title={t("leads.bySource")}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
                  <th scope="col" className="py-2">
                    {t("leads.source")}
                  </th>
                  <th scope="col" className="py-2 text-right">
                    {t("leads.enquiries")}
                  </th>
                  <th scope="col" className="py-2 text-right">
                    {t("leads.trials")}
                  </th>
                  <th scope="col" className="py-2 text-right">
                    {t("leads.joined")}
                  </th>
                  <th scope="col" className="py-2 text-right">
                    {t("leads.conversion")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {[...data.rows.filter((r) => r.enquiries > 0), data.total].map((r) => (
                  <tr
                    key={r.source}
                    className={r.source === "all" ? "font-semibold" : ""}
                  >
                    <th scope="row" className="py-2 text-left font-medium">
                      {r.source === "all"
                        ? t("leads.allSources")
                        : t(`leads.source.${r.source}` as MessageKey)}
                    </th>
                    <td className="py-2 text-right tabular-nums">{r.enquiries}</td>
                    <td className="py-2 text-right tabular-nums">{r.trials}</td>
                    <td className="py-2 text-right tabular-nums">{r.joined}</td>
                    <td className="py-2 text-right tabular-nums">{percent(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {data && data.top_referrers.length > 0 && (
        <Card title={t("leads.topReferrers")}>
          <ul className="divide-y divide-hairline text-sm">
            {data.top_referrers.map((r) => (
              <li key={r.member_id} className="flex justify-between gap-3 py-2">
                <Link
                  href={`/staff/members/${r.member_id}`}
                  className="font-medium hover:underline"
                >
                  {r.name} <span className="text-slate-500">{r.member_code}</span>
                </Link>
                <span className="text-slate-600">
                  {t("leads.referredCount", { referred: r.referred, joined: r.joined })}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
