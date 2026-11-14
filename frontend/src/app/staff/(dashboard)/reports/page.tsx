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
import {
  reportsApi,
  taxApi,
  type ClassesMonth,
  type MonthlyReport,
  type PtMonth,
  type TrendMonth,
} from "@/lib/api";
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
      {data.personal_training && <PersonalTraining pt={data.personal_training} />}
      {data.classes && <Classes month={data.classes} />}
      {data.shop && <Shop shop={data.shop} />}
      <VatBook month={data.month} />
    </div>
  );
}

/** The month's personal training (§18.3), for a gym that sells it. */
/** What was sold at the desk in the month (§20.1). */
/** A VAT-registered gym's month (§20.4): sales, returns, the VAT on them. */
function VatBook({ month }: { month: string }) {
  const { data } = useLoad(() => taxApi.book(month), [month]);
  if (!data || (data.invoices.length === 0 && data.returns.length === 0)) return null;
  return (
    <section className="space-y-3">
      <h2 className="pt-2 text-[0.9375rem] font-semibold text-slate-900">
        {t("tax.book")}
      </h2>
      <p className="text-sm text-slate-600">{t("tax.bookHelp")}</p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          value={<Money paisa={data.sales_total} />}
          label={t("tax.sales")}
          hint={t("tax.invoices", { count: data.invoices.length })}
        />
        <Stat value={<Money paisa={data.returns_total} />} label={t("tax.returns")} />
        <Stat
          value={<Money paisa={data.sales_vat - data.returns_vat} />}
          label={t("tax.vatNet")}
        />
      </div>
      <div className="flex flex-wrap gap-2 print:hidden">
        {(["sales-book", "sales-returns"] as const).map((kind) => (
          <Button
            key={kind}
            variant="secondary"
            onClick={() => reportsApi.download(kind)}
          >
            {t(`data.export.${kind}`)}
          </Button>
        ))}
      </div>
    </section>
  );
}

function Shop({ shop }: { shop: NonNullable<MonthlyReport["shop"]> }) {
  return (
    <section className="space-y-3">
      <h2 className="pt-2 text-[0.9375rem] font-semibold text-slate-900">
        {t("shop.title")}
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          value={<Money paisa={shop.income} />}
          label={t("reports.shop.income")}
          hint={t("reports.shop.incomeHelp")}
        />
        <Stat value={shop.sales} label={t("reports.shop.sales")} />
      </div>
      {shop.top.length > 0 && (
        <Card title={t("shop.topProducts")}>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-hairline">
              {shop.top.map((row) => (
                <tr key={row.name}>
                  <td className="py-2">{row.name}</td>
                  <td className="py-2 text-right text-slate-500">× {row.quantity}</td>
                  <td className="py-2 text-right font-semibold">
                    <Money paisa={row.amount} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  );
}

function PersonalTraining({ pt }: { pt: PtMonth }) {
  return (
    <section className="space-y-3">
      <h2 className="pt-2 text-[0.9375rem] font-semibold text-slate-900">
        {t("pt.title")}
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          value={<Money paisa={pt.income} />}
          label={t("reports.pt.income")}
          hint={t("reports.pt.incomeHelp")}
        />
        <Stat value={pt.sold} label={t("reports.pt.sold")} />
        <Stat value={pt.sessions} label={t("reports.pt.sessions")} />
        <Stat value={pt.members} label={t("reports.pt.members")} />
      </div>
      {pt.by_trainer.length > 0 && (
        <Card title={t("reports.pt.byTrainer")}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="py-1 font-medium">{t("pt.trainer")}</th>
                <th className="py-1 text-right font-medium">
                  {t("reports.pt.membersCol")}
                </th>
                <th className="py-1 text-right font-medium">
                  {t("reports.pt.sessionsCol")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {pt.by_trainer.map((row) => (
                <tr key={row.trainer_id}>
                  <td className="py-2">{row.name}</td>
                  <td className="py-2 text-right font-semibold">{row.members}</td>
                  <td className="py-2 text-right font-semibold">{row.sessions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  );
}

/** Classes held in the month (PLAN.md §19.4). */
function Classes({ month }: { month: ClassesMonth }) {
  return (
    <section className="space-y-3">
      <h2 className="pt-2 text-[0.9375rem] font-semibold text-slate-900">
        {t("reports.classes")}
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat value={month.held} label={t("reports.classes.held")} />
        <Stat
          value={month.booked}
          label={t("reports.classes.filled")}
          hint={t("reports.classes.filledOf", { places: month.places })}
        />
        <Stat value={month.came} label={t("reports.classes.came")} />
        <Stat value={month.no_shows} label={t("reports.classes.noShows")} />
      </div>
      {month.by_type.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          <Card title={t("reports.classes.byType")}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="py-1 font-medium">{t("classes.name")}</th>
                  <th className="py-1 text-right font-medium">
                    {t("reports.classes.heldCol")}
                  </th>
                  <th className="py-1 text-right font-medium">
                    {t("reports.classes.bookedCol")}
                  </th>
                  <th className="py-1 text-right font-medium">
                    {t("reports.classes.cameCol")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {month.by_type.map((row) => (
                  <tr key={row.name}>
                    <td className="py-2">{row.name}</td>
                    <td className="py-2 text-right font-semibold">{row.held}</td>
                    <td className="py-2 text-right font-semibold">
                      {row.booked} / {row.places}
                    </td>
                    <td className="py-2 text-right font-semibold">{row.came}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {month.by_instructor.length > 0 && (
            <Card title={t("reports.classes.byInstructor")}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="py-1 font-medium">{t("classes.instructor")}</th>
                    <th className="py-1 text-right font-medium">
                      {t("reports.classes.heldCol")}
                    </th>
                    <th className="py-1 text-right font-medium">
                      {t("reports.classes.cameCol")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {month.by_instructor.map((row) => (
                    <tr key={row.instructor_id}>
                      <td className="py-2">{row.name}</td>
                      <td className="py-2 text-right font-semibold">{row.held}</td>
                      <td className="py-2 text-right font-semibold">{row.came}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}
