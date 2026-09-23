"use client";

import Link from "next/link";
import { useState } from "react";

import { Notice } from "@/components/Notice";
import { methodLabel, METHODS } from "@/components/money/PaymentFields";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { DateInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { paymentsApi, type Method } from "@/lib/api";
import { formatDateTime, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Every payment, with totals by method for closing the till (§7). */
export default function PaymentsPage() {
  const { display } = useGymCalendar();
  const [from, setFrom] = useState(todayInNepal());
  const [to, setTo] = useState(todayInNepal());
  const [method, setMethod] = useState<Method | "">("");
  const { data, error } = useLoad(
    () =>
      paymentsApi.list({
        date_from: from,
        date_to: to,
        method: method || undefined,
        limit: 500,
      }),
    [from, to, method],
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("payments.title")} />
      <div className="grid gap-3 sm:grid-cols-3">
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
        <Select<Method | "all">
          label={t("payment.method")}
          value={method || "all"}
          onChange={(value) => setMethod(value === "all" ? "" : value)}
          options={[
            { value: "all", label: t("payments.allMethods") },
            ...METHODS.map((m) => ({ value: m, label: methodLabel(m) })),
          ]}
        />
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {data && (
        <>
          <Card>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
                  {t("payments.collected")}
                </p>
                <Money
                  paisa={data.sum_amount}
                  className="text-3xl font-bold tracking-tight text-slate-900"
                />
              </div>
              <dl className="flex flex-wrap gap-4 text-sm">
                {Object.entries(data.by_method).map(([m, amount]) => (
                  <div key={m}>
                    <dt className="text-xs text-slate-500">{methodLabel(m)}</dt>
                    <dd className="font-semibold">
                      <Money paisa={amount} />
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </Card>
          <Card title={t("payments.count", { count: data.total })}>
            {data.items.length === 0 && <EmptyState title={t("payment.none")} />}
            <ul className="divide-y divide-hairline">
              {data.items.map((p) => (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <div
                    className={`min-w-0 ${p.voided_at ? "text-slate-400 line-through" : ""}`}
                  >
                    <Link
                      href={`/staff/members/${p.member_id}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {p.member_name}
                    </Link>
                    <p className="text-xs text-slate-500">
                      #{p.receipt_no} · {methodLabel(p.method)}
                      {p.transaction_ref && ` · ${p.transaction_ref}`} ·{" "}
                      {formatDateTime(p.paid_at, display)}
                      {p.received_by_name && ` · ${p.received_by_name}`}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <Money
                      paisa={p.kind === "refund" ? -p.amount : p.amount}
                      className={`font-semibold ${p.voided_at ? "text-slate-400 line-through" : ""}`}
                    />
                    <Link
                      href={`/staff/receipts/${p.id}`}
                      className="block text-xs text-brand-700 hover:underline"
                    >
                      {t("payment.receipt")}
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
