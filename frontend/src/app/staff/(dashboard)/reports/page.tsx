"use client";

import { Printer } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { compactRupees } from "@/components/charts/scale";
import { categoryLabel } from "@/components/money/ExpenseDialog";
import { methodLabel } from "@/components/money/PaymentFields";
import { Delta } from "@/components/today/Delta";
import { Card, PageHeader, Stat } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { MonthSwitcher } from "@/components/ui/MonthSwitcher";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { t } from "@/i18n";
import { reportsApi, type TrendMonth } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { formatRs } from "@/lib/money";
import { monthName } from "@/lib/months";
import { useLoad } from "@/lib/useLoad";

/**
 * Reports (PLAN.md §7, §16.2 7.9): one month's figures, each against the
 * month before, and the last twelve months as charts.
 */
export default function ReportsPage() {
  const { display } = useGymCalendar();
  const [month, setMonth] = useState<string | undefined>(undefined);
  const { data } = useLoad(() => reportsApi.monthly(month), [month]);
  const trend = useLoad(() => reportsApi.trend(month), [month]);
  if (!data) return <PageSkeleton label={t("common.loading")} />;

  const months = trend.data?.months ?? [];
  const calendar = data.calendar;
  const previous: TrendMonth | undefined = months[months.length - 2];
  const labels = months.map((m) => monthName(m.month, calendar));
  const shown = (pick: (m: TrendMonth) => number | null) =>
    months.map((m) => (m.started ? pick(m) : null));
  const rate =
    data.renewal_rate === null ? "—" : `${Math.round(data.renewal_rate * 100)}%`;
  const vs = (now: number, before: number | undefined, goodWhenUp = true) =>
    previous?.started && before !== undefined ? (
      <Delta now={now} before={before} period="lastMonth" goodWhenUp={goodWhenUp} />
    ) : undefined;
  const vsRs = (now: number, before: number | undefined, goodWhenUp = true) =>
    previous?.started && before !== undefined ? (
      <Delta
        now={now}
        before={before}
        period="lastMonth"
        goodWhenUp={goodWhenUp}
        format={(paisa) => formatRs(paisa)}
      />
    ) : undefined;
  const spent = Object.entries(data.expenses_by_category).sort(([, a], [, b]) => b - a);

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("reports.title")}
        subtitle={`${formatDate(data.first_day, display)} → ${formatDate(data.last_day, display)}`}
        actions={
          <Button variant="secondary" onClick={() => window.print()}>
            <Printer className="size-4" aria-hidden />
            {t("reports.print")}
          </Button>
        }
      />
      <MonthSwitcher month={data.month} calendar={calendar} onChange={setMonth} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          value={<Money paisa={data.income} />}
          label={t("reports.income")}
          hint={vsRs(data.income, previous?.income)}
        />
        <Stat
          value={<Money paisa={data.expenses} />}
          label={t("reports.spent")}
          hint={vsRs(data.expenses, previous?.expenses, false)}
        />
        <Stat
          value={<Money paisa={data.profit} />}
          label={t("reports.profit")}
          tone={data.profit < 0 ? "danger" : "plain"}
          hint={vsRs(data.profit, previous?.profit)}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          value={data.new_members}
          label={t("reports.newMembers")}
          hint={vs(data.new_members, previous?.new_members)}
        />
        <Stat
          value={data.renewals}
          label={t("reports.renewals")}
          hint={vs(data.renewals, previous?.renewals)}
        />
        <Stat
          value={data.lapsed}
          label={t("reports.lapsed")}
          hint={vs(data.lapsed, previous?.lapsed, false)}
        />
        <Stat
          value={data.active_members}
          label={t("reports.active")}
          hint={vs(data.active_members, previous?.active_members)}
        />
        <Stat
          value={rate}
          label={t("reports.renewalRate", {
            renewed: data.renewed,
            due: data.due_to_renew,
          })}
        />
        <Stat value={data.new_memberships} label={t("reports.firstMemberships")} />
        <Stat
          value={data.visits}
          label={t("reports.visits")}
          hint={vs(data.visits, previous?.visits)}
        />
      </div>

      {months.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={t("reports.moneyByMonth")} className="min-w-0">
            <BarChart
              title={t("reports.moneyByMonth")}
              labels={labels}
              series={[
                {
                  key: "income",
                  label: t("reports.income"),
                  values: months.map((m) => m.income),
                },
                {
                  key: "spent",
                  label: t("reports.spent"),
                  values: months.map((m) => m.expenses),
                },
              ]}
              format={(paisa) => formatRs(paisa)}
              tickFormat={compactRupees}
            />
          </Card>
          <Card title={t("reports.activeByMonth")} className="min-w-0">
            <LineChart
              title={t("reports.activeByMonth")}
              labels={labels}
              series={[
                {
                  key: "active",
                  label: t("reports.active"),
                  values: shown((m) => m.active_members),
                },
              ]}
            />
          </Card>
          <Card title={t("reports.newVsLapsed")} className="min-w-0">
            <BarChart
              title={t("reports.newVsLapsed")}
              labels={labels}
              series={[
                {
                  key: "new",
                  label: t("reports.newMembers"),
                  values: months.map((m) => m.new_members),
                },
                {
                  key: "lapsed",
                  label: t("reports.lapsed"),
                  values: months.map((m) => m.lapsed),
                },
              ]}
            />
          </Card>
          <Card title={t("reports.renewalByMonth")} className="min-w-0">
            <LineChart
              title={t("reports.renewalByMonth")}
              labels={labels}
              max={100}
              format={(value) => `${value}%`}
              tickFormat={(value) => `${value}%`}
              series={[
                {
                  key: "rate",
                  label: t("reports.renewalByMonth"),
                  values: shown((m) =>
                    m.renewal_rate === null ? null : Math.round(m.renewal_rate * 100),
                  ),
                },
              ]}
            />
          </Card>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card title={t("reports.spentByCategory")}>
          {spent.length === 0 ? (
            <p className="text-sm text-slate-500">
              {t("reports.noExpenses")}{" "}
              <Link
                href="/staff/expenses"
                className="font-medium text-brand-700 hover:underline print:hidden"
              >
                {t("nav.expenses")}
              </Link>
            </p>
          ) : (
            <dl className="divide-y divide-hairline text-sm">
              {spent.map(([category, amount]) => (
                <div key={category} className="flex justify-between py-2">
                  <dt>{categoryLabel(category)}</dt>
                  <dd className="font-semibold">
                    <Money paisa={amount} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
        <Card title={t("reports.byMethod")}>
          <dl className="divide-y divide-hairline text-sm">
            {Object.entries(data.income_by_method).map(([method, amount]) => (
              <div key={method} className="flex justify-between py-2">
                <dt>{methodLabel(method)}</dt>
                <dd className="font-semibold">
                  <Money paisa={amount} />
                </dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title={t("reports.byPlan")}>
          <dl className="divide-y divide-hairline text-sm">
            {Object.entries(data.by_plan).map(([plan, count]) => (
              <div key={plan} className="flex justify-between py-2">
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
