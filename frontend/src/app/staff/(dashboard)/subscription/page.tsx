"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader, Row } from "@/components/ui/Card";
import { MoneyInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, subscriptionApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Our plan with the gym: days left, SMS credits, and paying us (§5.7). */
export default function SubscriptionPage() {
  const { refreshMe } = useAuth();
  const { display } = useGymCalendar();
  const { data, reload } = useLoad(() => subscriptionApi.overview(), []);
  const [kind, setKind] = useState<"subscription" | "sms">("subscription");
  const [planId, setPlanId] = useState("");
  const [months, setMonths] = useState("1");
  const [credits, setCredits] = useState("500");
  const [amount, setAmount] = useState<number | null>(null);
  const [ref, setRef] = useState("");
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  const plan = data.plans.find((p) => p.id === (planId || data.plans[0]?.id));
  const suggested =
    kind === "subscription" && plan?.monthly_price
      ? plan.monthly_price * Number(months)
      : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await subscriptionApi.pay({
        kind,
        platform_plan_id: kind === "subscription" ? plan?.id : null,
        months: kind === "subscription" ? Number(months) : null,
        sms_credits: kind === "sms" ? Number(credits) : null,
        amount: amount ?? suggested ?? 0,
        transaction_ref: ref,
      });
      setRef("");
      setMessage({ tone: "success", text: t("subscription.sent") });
      reload();
      await refreshMe();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.subscription")} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card title={data.plan_name ?? t("subscription.none")}>
          <dl>
            <Row label={t("subscription.status")}>
              {t(`subscription.phase.${data.phase}` as MessageKey)}
            </Row>
            <Row label={t("subscription.until")}>
              {formatDate(data.ends_on, display)}
            </Row>
            <Row label={t("subscription.daysLeft")}>{data.days_left}</Row>
            <Row label={t("subscription.members")}>
              {data.active_members}
              {data.max_active_members !== null && ` / ${data.max_active_members}`}
            </Row>
            <Row label={t("sms.balance")}>{data.sms_balance}</Row>
          </dl>
          {data.over_limit && (
            <div className="mt-2">
              <Notice tone="warning">{t("subscription.banner.overLimit")}</Notice>
            </div>
          )}
        </Card>
        <Card title={t("subscription.payTo")}>
          <p className="text-sm text-slate-600">{t("subscription.payHelp")}</p>
          <dl className="mt-2">
            {data.pay_to.name && (
              <Row label={t("paymentMethods.accountName")}>{data.pay_to.name}</Row>
            )}
            {data.pay_to.esewa && (
              <Row label={t("account.esewa")}>{data.pay_to.esewa}</Row>
            )}
            {data.pay_to.bank && (
              <Row label={t("account.bank")}>{data.pay_to.bank}</Row>
            )}
          </dl>
          {!data.pay_to.name && !data.pay_to.esewa && !data.pay_to.bank && (
            <p className="mt-2 text-sm text-slate-500">
              {t("subscription.payToMissing")}
            </p>
          )}
        </Card>
      </div>

      <Card title={t("subscription.sendPayment")}>
        <form onSubmit={(e) => void submit(e)} className="space-y-3">
          <div className="flex gap-2">
            {(["subscription", "sms"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`rounded-full border px-3 py-1 text-sm ${kind === k ? "border-brand-600 bg-brand-50" : "border-slate-300"}`}
              >
                {t(`subscription.kind.${k}` as MessageKey)}
              </button>
            ))}
          </div>
          {kind === "subscription" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                label={t("subscription.plan")}
                value={plan?.id ?? ""}
                onChange={setPlanId}
                options={data.plans.map((p) => ({
                  value: p.id,
                  label: `${p.name}${p.monthly_price !== null ? ` — ${(p.monthly_price / 100).toLocaleString("en-IN")}/${t("subscription.month")}` : ""}`,
                }))}
              />
              <Field
                label={t("subscription.months")}
                value={months}
                onChange={setMonths}
                type="number"
                inputMode="numeric"
                required
              />
            </div>
          ) : (
            <Field
              label={t("subscription.credits")}
              value={credits}
              onChange={setCredits}
              type="number"
              inputMode="numeric"
              required
            />
          )}
          <MoneyInput
            label={t("subscription.amountPaid")}
            value={amount ?? suggested}
            onChange={setAmount}
            required
          />
          <Field
            label={t("payment.transactionRef")}
            value={ref}
            onChange={setRef}
            required
          />
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          <Button type="submit">{t("subscription.send")}</Button>
        </form>
      </Card>

      {data.payments.length > 0 && (
        <Card title={t("subscription.history")}>
          <ul className="divide-y divide-hairline text-sm">
            {data.payments.map((p) => (
              <li key={p.id} className="flex justify-between py-2">
                <span>
                  {p.kind === "sms"
                    ? t("subscription.smsCredits", { count: p.sms_credits ?? 0 })
                    : `${p.plan_name} × ${p.months}`}
                  <span className="block text-xs text-slate-500">
                    {p.transaction_ref} ·{" "}
                    {t(`subscription.payment.${p.status}` as MessageKey)}
                    {p.reject_reason && ` — ${p.reject_reason}`}
                  </span>
                </span>
                <Money paisa={p.amount} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
