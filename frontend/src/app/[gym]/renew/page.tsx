"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { errorMessage, type Plan } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatRs } from "@/lib/money";
import { shrinkImage } from "@/lib/image";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLive } from "@/lib/live";
import { perMonth, savings } from "@/lib/planValue";
import { useLoad } from "@/lib/useLoad";

/** Plan → Pay → Send proof, with where they are (PLAN.md §16.3, 8.5). */
function Steps({ at }: { at: 1 | 2 | 3 }) {
  const steps = [
    t("app.renew.step.plan"),
    t("app.renew.step.pay"),
    t("app.renew.step.proof"),
  ];
  return (
    <ol
      className="flex items-center gap-2 text-xs font-semibold"
      aria-label={t("app.renew.steps")}
    >
      {steps.map((label, i) => {
        const n = i + 1;
        const state = n < at ? "done" : n === at ? "current" : "next";
        return (
          <li
            key={label}
            aria-current={state === "current" ? "step" : undefined}
            className="flex flex-1 items-center gap-1.5"
          >
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
                state === "next"
                  ? "bg-slate-100 text-slate-500"
                  : "bg-brand-600 text-white"
              }`}
            >
              {state === "done" ? "✓" : n}
            </span>
            <span className={state === "next" ? "text-slate-500" : "text-slate-900"}>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Plans -> the gym's payment QR -> transaction ID or screenshot -> waiting for
 * the gym to confirm (§5.2). The money goes to the gym, never to GymBhai.
 */
export default function RenewPage() {
  const { me } = useMember();
  const options = useLoad(() => memberApi.renewOptions(), []);
  const mine = useLoad(() => memberApi.payments(), []);
  // Approved or rejected while they wait on this screen.
  useLive(["payment_request", "member"], () => {
    mine.reload();
    options.reload();
  });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [methodId, setMethodId] = useState<string | null>(null);
  const [ref, setRef] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!me) return null;
  const display = me.gym.date_display;
  const waiting = mine.data?.requests.find((r) => r.status === "pending");
  const lastRejected = mine.data?.requests.find((r) => r.status === "rejected");

  if (waiting) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-4xl">⏳</p>
        <h1 className="text-xl font-semibold">{t("app.renew.waiting")}</h1>
        <p className="text-slate-600">
          {t("app.renew.waitingDetail", { plan: waiting.plan_name ?? "" })}{" "}
          <Money paisa={waiting.amount} />
        </p>
        <Button
          variant="secondary"
          onClick={async () => {
            await memberApi.withdraw(waiting.id);
            mine.reload();
          }}
        >
          {t("app.renew.withdraw")}
        </Button>
      </div>
    );
  }
  if (!options.data)
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const { plans, payment_methods: methods } = options.data;
  // Whoever pays for a family or couple plan renews it for everyone on it
  // (§19.1): each newcomer's admission fee too.
  const mates = plan && plan.seats > 1 ? (options.data.renew_with ?? []) : [];
  const newcomers =
    (options.data.first_membership ? 1 : 0) +
    mates.filter((m) => m.first_membership).length;
  const admission = (plan?.admission_fee ?? 0) * newcomers;
  const total = (plan?.price ?? 0) + admission;
  const method = methods.find((m) => m.id === methodId);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!plan) return;
    if (!ref.trim() && !screenshot) return setError(t("app.renew.needProof"));
    setPending(true);
    setError(null);
    try {
      const created = await memberApi.createRequest({
        plan_id: plan.id,
        payment_method_id: methodId,
        amount: total,
        transaction_ref: ref.trim() || null,
      });
      if (screenshot)
        await memberApi.uploadScreenshot(created.id, await shrinkImage(screenshot));
      mine.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-5">
      <h1 className="text-xl font-semibold">{t("app.renew.title")}</h1>
      <Steps at={!plan ? 1 : !methodId ? 2 : 3} />
      {lastRejected && (
        <Notice tone="warning">
          {t("app.renew.rejected", { reason: lastRejected.reject_reason ?? "" })}
        </Notice>
      )}
      <p className="text-sm text-slate-600">
        {t("app.renew.startsOn", {
          date: formatDate(options.data.renewal_starts_on, display),
        })}
      </p>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-semibold">
          {t("app.renew.choosePlan")}
        </legend>
        {plans.map((p) => {
          const monthly = perMonth(p);
          const saved = savings(p, plans);
          return (
            <label
              key={p.id}
              className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl border p-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 ${
                plan?.id === p.id
                  ? "border-brand-600 bg-brand-50"
                  : "border-transparent bg-white ring-1 ring-hairline"
              }`}
            >
              <input
                type="radio"
                name="plan"
                className="sr-only"
                checked={plan?.id === p.id}
                onChange={() => setPlan(p)}
              />
              <span className="min-w-0">
                <span className="block font-medium">{p.name}</span>
                {p.seats > 1 && (
                  <span className="block text-xs text-slate-500">
                    {t("plans.forPeople", { count: p.seats })}
                  </span>
                )}
                {monthly !== null && p.duration_months! > 1 && (
                  <span className="block text-xs text-slate-500">
                    {t("app.renew.perMonth", { amount: formatRs(monthly) })}
                  </span>
                )}
              </span>
              <span className="shrink-0 text-right">
                <Money paisa={p.price} className="block font-semibold" />
                {saved !== null && (
                  <span className="mt-0.5 inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200/70">
                    {t("app.renew.save", { amount: formatRs(saved) })}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </fieldset>

      {plan && (
        <>
          <div className="rounded-xl bg-white p-3 text-sm">
            {mates.length > 0 && (
              <p className="mb-1 text-slate-600">
                {t("app.renew.forEveryone", {
                  names: mates.map((m) => m.name).join(", "),
                })}
              </p>
            )}
            {admission > 0 && (
              <p className="flex justify-between">
                <span>{t("sale.admissionFee")}</span>
                <Money paisa={admission} />
              </p>
            )}
            <p className="flex justify-between text-base font-semibold">
              <span>{t("app.renew.pay")}</span>
              <Money paisa={total} />
            </p>
          </div>

          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-semibold">
              {t("app.renew.payTo")}
            </legend>
            {methods.length === 0 && <Notice>{t("app.renew.noMethods")}</Notice>}
            <div className="flex flex-wrap gap-2">
              {methods.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMethodId(m.id)}
                  className={`rounded-full border px-4 py-1.5 text-sm ${
                    methodId === m.id
                      ? "border-brand-600 bg-brand-50"
                      : "border-slate-300"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {method && (
              <div className="rounded-xl bg-white p-4 text-center">
                {method.qr_image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={method.qr_image_url} alt="" className="mx-auto w-56" />
                )}
                <p className="mt-2 font-medium">{method.account_name}</p>
                <p className="text-sm text-slate-600">{method.account_number}</p>
                <p className="mt-2 text-xs text-slate-500">
                  {t("app.renew.payInWallet")}
                </p>
              </div>
            )}
          </fieldset>

          <Field
            label={t("payment.transactionRef")}
            value={ref}
            onChange={setRef}
            help={t("app.renew.refHelp")}
          />
          <label className="block text-sm">
            <span className="font-medium">{t("app.renew.screenshot")}</span>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setScreenshot(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm"
            />
          </label>
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" block disabled={pending}>
            {t("app.renew.sent")}
          </Button>
        </>
      )}
    </form>
  );
}
