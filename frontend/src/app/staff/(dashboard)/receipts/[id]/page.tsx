"use client";

import { useParams } from "next/navigation";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { methodLabel } from "@/components/money/PaymentFields";
import { Row } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { paymentsApi } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

/**
 * A payment receipt — not a VAT invoice, and it says so (PLAN.md §10).
 * Sized to print on A5 or a phone screenshot.
 */
export default function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error } = useLoad(() => paymentsApi.receipt(id), [id]);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!r) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const p = r.payment;
  const date = (iso: string | null) => formatDate(iso, r.date_display);

  return (
    <div className="mx-auto max-w-md">
      <div className="mb-4 flex justify-end gap-2 print:hidden">
        <Button variant="secondary" onClick={() => window.history.back()}>
          {t("common.back")}
        </Button>
        <Button onClick={() => window.print()}>{t("receipt.print")}</Button>
      </div>
      <article className="rounded-2xl bg-surface p-6 shadow-card ring-1 ring-hairline print:p-0 print:ring-0">
        <header className="border-b border-dashed border-slate-300 pb-3 text-center">
          <h1 className="text-xl font-bold">{r.gym_name}</h1>
          {r.branch_name && <p className="text-sm text-slate-600">{r.branch_name}</p>}
          {r.gym_address && <p className="text-sm text-slate-600">{r.gym_address}</p>}
          {r.gym_phone && <p className="text-sm text-slate-600">{r.gym_phone}</p>}
          <p className="mt-2 text-sm font-semibold uppercase tracking-wide">
            {p.kind === "refund" ? t("receipt.refundTitle") : t("receipt.title")}
          </p>
        </header>
        {p.voided_at && (
          <p className="mt-3 rounded bg-red-50 p-2 text-center text-sm font-semibold text-red-800">
            {t("receipt.voided", { reason: p.void_reason ?? "" })}
          </p>
        )}
        <dl className="mt-3">
          <Row label={t("receipt.number")}>#{p.receipt_no}</Row>
          <Row label={t("receipt.date")}>
            {formatDateTime(p.paid_at, r.date_display)}
          </Row>
          <Row label={t("receipt.member")}>
            {r.member_name} ({r.member_code})
          </Row>
          {r.plan_name && <Row label={t("sale.plan")}>{r.plan_name}</Row>}
          {r.start_date && (
            <Row label={t("receipt.period")}>
              {date(r.start_date)} → {date(r.end_date)}
            </Row>
          )}
          <Row label={t("payment.method")}>{methodLabel(p.method)}</Row>
          {p.transaction_ref && (
            <Row label={t("payment.transactionRef")}>{p.transaction_ref}</Row>
          )}
        </dl>
        <div className="mt-3 flex items-center justify-between border-t border-dashed border-slate-300 pt-3">
          <span className="font-semibold">{t("receipt.amount")}</span>
          <Money paisa={p.amount} className="text-2xl font-bold" />
        </div>
        {r.dues_after !== null && r.dues_after > 0 && (
          <p className="mt-1 text-right text-sm text-amber-800">
            {t("receipt.duesAfter")} <Money paisa={r.dues_after} />
          </p>
        )}
        {p.received_by_name && (
          <p className="mt-3 text-sm text-slate-600">
            {t("receipt.receivedBy", { name: p.received_by_name })}
          </p>
        )}
        <p className="mt-4 text-center text-xs text-slate-500">
          {t("receipt.notInvoice")}
        </p>
      </article>
    </div>
  );
}
