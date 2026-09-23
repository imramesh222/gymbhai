"use client";

import { methodLabel } from "@/components/money/PaymentFields";
import { Money } from "@/components/ui/Money";
import { EmptyState } from "@/components/ui/Card";
import { t, type MessageKey } from "@/i18n";
import { formatDateTime } from "@/lib/dates";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

export default function MemberPayments() {
  const { me } = useMember();
  const { data } = useLoad(() => memberApi.payments(), []);
  if (!me || !data)
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const display = me.gym.date_display;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("app.tab.payments")}</h1>
      {data.dues > 0 && (
        <p className="rounded-xl bg-amber-50 p-3 text-amber-900">
          {t("app.home.owes")} <Money paisa={data.dues} className="font-semibold" />
        </p>
      )}
      {data.requests.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-600">
            {t("app.payments.requests")}
          </h2>
          <ul className="space-y-2">
            {data.requests.map((r) => (
              <li key={r.id} className="rounded-xl bg-white p-3 text-sm">
                <div className="flex justify-between">
                  <span>{r.plan_name}</span>
                  <Money paisa={r.amount} />
                </div>
                <p className="text-xs text-slate-500">
                  {t(`app.request.${r.status}` as MessageKey)}
                  {r.reject_reason && ` — ${r.reject_reason}`}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">
          {t("app.payments.paid")}
        </h2>
        {data.payments.length === 0 && <EmptyState title={t("payment.none")} />}
        <ul className="space-y-2">
          {data.payments.map((p) => (
            <li
              key={p.id}
              className="flex justify-between rounded-xl bg-white p-3 text-sm"
            >
              <div>
                <p className="font-medium">
                  {p.kind === "refund" ? t("payment.refund") : methodLabel(p.method)}
                </p>
                <p className="text-xs text-slate-500">
                  #{p.receipt_no} · {formatDateTime(p.paid_at, display)}
                </p>
              </div>
              <Money
                paisa={p.kind === "refund" ? -p.amount : p.amount}
                className="font-semibold"
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
