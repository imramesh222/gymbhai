"use client";

import Link from "next/link";

import { methodLabel } from "@/components/money/PaymentFields";
import { Money } from "@/components/ui/Money";
import { EmptyState } from "@/components/ui/Card";
import { t } from "@/i18n";
import type { Payment } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";

export function PaymentsTable({ payments }: { payments: Payment[] }) {
  const { display } = useGymCalendar();
  if (payments.length === 0) {
    return <EmptyState title={t("payment.none")} />;
  }
  return (
    <ul className="divide-y divide-hairline">
      {payments.map((p) => (
        <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
          <div
            className={`min-w-0 ${p.voided_at ? "text-slate-400 line-through" : ""}`}
          >
            <p className="font-medium">
              {p.kind === "refund" ? t("payment.refund") : methodLabel(p.method)}
              {p.transaction_ref && (
                <span className="font-normal text-slate-500">
                  {" "}
                  · {p.transaction_ref}
                </span>
              )}
            </p>
            <p className="text-xs text-slate-500">
              #{p.receipt_no} · {formatDateTime(p.paid_at, display)}
              {p.received_by_name && ` · ${p.received_by_name}`}
            </p>
            {p.voided_at && (
              <p className="text-xs text-red-700 no-underline">
                {t("payment.voidedBecause", { reason: p.void_reason ?? "" })}
              </p>
            )}
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
  );
}
