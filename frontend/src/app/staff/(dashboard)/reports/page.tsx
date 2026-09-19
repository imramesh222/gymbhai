"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { methodLabel } from "@/components/money/PaymentFields";
import { Card, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { reportsApi } from "@/lib/api";
import { BS_MONTHS, formatDate } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

const AD_MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function shift(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) + by;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** Monthly: income by method, new members, renewals, lapsed, renewal rate (§7). */
export default function ReportsPage() {
  const { display } = useGymCalendar();
  const [month, setMonth] = useState<string | undefined>(undefined);
  const { data } = useLoad(() => reportsApi.monthly(month), [month]);
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const [year, number] = data.month.split("-").map(Number);
  const title = `${(data.calendar === "bs" ? BS_MONTHS : AD_MONTHS)[number - 1]} ${year}`;
  const rate =
    data.renewal_rate === null ? "—" : `${Math.round(data.renewal_rate * 100)}%`;

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("reports.title")}
        subtitle={`${formatDate(data.first_day, display)} → ${formatDate(data.last_day, display)}`}
      />
      <div className="flex items-center justify-between rounded-xl bg-white p-2">
        <Button variant="ghost" onClick={() => setMonth(shift(data.month, -1))}>
          ← {t("common.previous")}
        </Button>
        <p className="font-semibold">{title}</p>
        <Button variant="ghost" onClick={() => setMonth(shift(data.month, 1))}>
          {t("common.next")} →
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          [<Money key="i" paisa={data.income} />, t("reports.income")],
          [data.new_members, t("reports.newMembers")],
          [data.renewals, t("reports.renewals")],
          [data.lapsed, t("reports.lapsed")],
          [data.active_members, t("reports.active")],
          [
            rate,
            t("reports.renewalRate", { renewed: data.renewed, due: data.due_to_renew }),
          ],
          [data.new_memberships, t("reports.firstMemberships")],
          [data.visits, t("reports.visits")],
        ].map(([value, label], i) => (
          <Card key={i}>
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-xs text-slate-500">{label}</p>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={t("reports.byMethod")}>
          <dl className="space-y-1 text-sm">
            {Object.entries(data.income_by_method).map(([method, amount]) => (
              <div key={method} className="flex justify-between">
                <dt>{methodLabel(method)}</dt>
                <dd className="font-semibold">
                  <Money paisa={amount} />
                </dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title={t("reports.byPlan")}>
          <dl className="space-y-1 text-sm">
            {Object.entries(data.by_plan).map(([plan, count]) => (
              <div key={plan} className="flex justify-between">
                <dt>{plan}</dt>
                <dd className="font-semibold">{count}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </div>
  );
}
