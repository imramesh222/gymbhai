"use client";

import { XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { methodLabel } from "@/components/money/PaymentFields";
import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { TextArea } from "@/components/ui/inputs";
import { Menu } from "@/components/ui/Menu";
import { Money } from "@/components/ui/Money";
import { MonthSwitcher } from "@/components/ui/MonthSwitcher";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { errorMessage, shopApi, type ProductSale, type SalesMonth } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";

import { categoryLabel } from "./Till";

/** A month of the shop's sales, with what they add up to (PLAN.md §20.1). */
export function SalesList({
  data,
  onMonth,
  onChanged,
}: {
  data: SalesMonth;
  onMonth: (month: string) => void;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const { display } = useGymCalendar();
  const toast = useToast();
  const [voiding, setVoiding] = useState<ProductSale | null>(null);
  const byCategory = Object.entries(data.by_category).sort(([, a], [, b]) => b - a);
  return (
    <div className="space-y-4">
      <MonthSwitcher month={data.month} calendar={data.calendar} onChange={onMonth} />
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
              {t("shop.takings")}
            </p>
            <Money
              paisa={data.total}
              className="text-3xl font-bold tracking-tight text-slate-900"
            />
            <p className="text-xs text-slate-500">
              {t("shop.salesCount", { count: data.count })}
            </p>
          </div>
          {byCategory.length > 0 && (
            <dl
              className="flex flex-wrap gap-4 text-sm"
              aria-label={t("shop.byCategory")}
            >
              {byCategory.map(([category, amount]) => (
                <div key={category}>
                  <dt className="text-xs text-slate-500">{categoryLabel(category)}</dt>
                  <dd className="font-semibold">
                    <Money paisa={amount ?? 0} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        {data.top.length > 0 && (
          <div className="mt-3 border-t border-hairline pt-3">
            <p className="text-xs font-semibold text-slate-500">
              {t("shop.topProducts")}
            </p>
            <ol className="mt-1 space-y-0.5 text-sm">
              {data.top.map((p) => (
                <li key={p.name} className="flex justify-between gap-3">
                  <span>
                    {p.name} <span className="text-slate-500">× {p.quantity}</span>
                  </span>
                  <Money paisa={p.amount} />
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
      <Card title={t("shop.sales")}>
        {data.items.length === 0 && <EmptyState title={t("shop.noSales")} />}
        <ul className="divide-y divide-hairline">
          {data.items.map((sale) => {
            const voided = Boolean(sale.voided_at);
            return (
              <li
                key={sale.id}
                className="flex items-center justify-between gap-3 py-2.5 text-sm"
              >
                <div className={`min-w-0 ${voided ? "text-slate-500" : ""}`}>
                  <p
                    className={`font-medium text-slate-900 ${voided ? "line-through" : ""}`}
                  >
                    {sale.lines.map((l) => `${l.quantity} × ${l.name}`).join(", ")}
                  </p>
                  <p className="text-xs text-slate-500">
                    {sale.member_id ? (
                      <Link
                        href={`/staff/members/${sale.member_id}`}
                        className="hover:underline"
                      >
                        {sale.member_name}
                      </Link>
                    ) : (
                      t("shop.walkIn")
                    )}
                    {" · "}
                    {formatDateTime(sale.sold_at, display)}
                    {sale.method && ` · ${methodLabel(sale.method)}`}
                    {sale.created_by_name && ` · ${sale.created_by_name}`}
                  </p>
                  {voided && sale.void_reason && (
                    <p className="text-xs text-red-600">
                      {t("payment.voidedBecause", { reason: sale.void_reason })}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <div className="text-right">
                    <Money
                      paisa={sale.total}
                      className={`font-semibold ${voided ? "text-slate-500 line-through" : ""}`}
                    />
                    {sale.payment_id && (
                      <Link
                        href={`/staff/receipts/${sale.payment_id}`}
                        className="block text-xs text-brand-700 hover:underline"
                      >
                        #{sale.receipt_no}
                      </Link>
                    )}
                  </div>
                  <Menu
                    compact
                    items={[
                      {
                        label: t("shop.void"),
                        icon: XCircle,
                        danger: true,
                        hidden: voided || !can("payments.void"),
                        onSelect: () => setVoiding(sale),
                      },
                    ]}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
      {voiding && (
        <VoidSale
          onClose={() => setVoiding(null)}
          onVoid={async (reason) => {
            await shopApi.voidSale(voiding.id, reason);
            toast.success(t("shop.voided"));
            setVoiding(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function VoidSale({
  onClose,
  onVoid,
}: {
  onClose: () => void;
  onVoid: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  return (
    <Dialog open onClose={onClose} title={t("shop.void")}>
      <form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault();
          if (saving) return;
          setSaving(true);
          try {
            await onVoid(reason);
          } catch (err) {
            setError(errorMessage(err));
            setSaving(false);
          }
        }}
      >
        <p className="text-sm text-slate-600">{t("shop.voidHelp")}</p>
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block disabled={saving}>
          {t("shop.void")}
        </Button>
      </form>
    </Dialog>
  );
}
