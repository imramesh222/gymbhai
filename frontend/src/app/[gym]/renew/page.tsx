"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import {
  CheckoutBar,
  MethodOption,
  PlanOption,
  StatusPanel,
  Step,
  WalletBadge,
} from "@/components/memberApp/RenewParts";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, type Plan } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/dates";
import { formatRs } from "@/lib/money";
import { shrinkImage } from "@/lib/image";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLive } from "@/lib/live";
import { bestValue, perMonth, savings } from "@/lib/planValue";
import { useLoad } from "@/lib/useLoad";

/** The gym's QR as a file, to open from the gallery in a wallet app. */
async function saveQr(url: string, name: string) {
  try {
    const blob = await (await fetch(url)).blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
  } catch {
    // Somewhere that won't let us read it: the image itself, to save by hand.
    window.open(url, "_blank", "noopener");
  }
}

/** Bring the next step into view once it appears. */
function reveal(el: HTMLElement | null) {
  setTimeout(() => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView?.({ behavior: still ? "auto" : "smooth", block: "start" });
  }, 60);
}

/**
 * Renew (PLAN.md §5.2, §16.3 8.5, §20.2), as on the phone app: choose a plan,
 * choose how to pay, pay. Nothing is chosen for the member. An account the
 * wallet confirms goes to the wallet's own page and back; any other shows the
 * gym's QR, then the transaction ID or a screenshot, and waits for the gym.
 * The total and the next step stay in a bar above the tabs. The money goes to
 * the gym, never to GymBhai.
 */
export default function RenewPage() {
  const { me, slug } = useMember();
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
  const [screenshot, setScreenshot] = useState<{ file: File; url: string } | null>(
    null,
  );
  const [needProof, setNeedProof] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // An account the wallet confirms (§20.2): its page, unless they'd rather
  // pay the QR and send the transaction ID.
  const [byHand, setByHand] = useState(false);
  // "You're renewed" is for an answer that came while the page was open.
  const [openedAt] = useState(Date.now);
  const [seen, setSeen] = useState<string | null>(null);
  const payStep = useRef<HTMLDivElement>(null);
  const finishStep = useRef<HTMLDivElement>(null);

  function pickScreenshot(file: File | null) {
    if (screenshot) URL.revokeObjectURL(screenshot.url);
    setScreenshot(file && { file, url: URL.createObjectURL(file) });
    if (file) setNeedProof(false);
  }

  /** Back to an empty page: nothing chosen for them, ever. */
  function clear() {
    setPlan(null);
    setMethodId(null);
    setRef("");
    pickScreenshot(null);
    setNeedProof(false);
    setByHand(false);
    setError(null);
  }

  if (!me) return null;
  if (!options.data || !mine.data) {
    const failed = options.error ?? mine.error;
    return failed ? (
      <Notice tone="error">{failed}</Notice>
    ) : (
      <p className="text-sm text-slate-500">{t("common.loading")}</p>
    );
  }
  const display = me.gym.date_display;
  const { state } = me;

  // --- whole-page states -------------------------------------------------------

  const waiting = mine.data.requests.find((r) => r.status === "pending");
  if (waiting) {
    const wallet = waiting.confirmed_by
      ? t(`account.${waiting.confirmed_by}` as MessageKey)
      : null;
    return (
      <StatusPanel
        tone="waiting"
        title={wallet ? t("pay.paidForDesk") : t("app.renew.waiting")}
        note={wallet ? undefined : t("app.renew.waitingNote")}
        lines={[
          { label: t("app.renew.planLine"), value: waiting.plan_name ?? "" },
          { label: t("app.renew.amountLine"), value: formatRs(waiting.amount) },
          ...(waiting.method_label
            ? [{ label: t("app.renew.methodLine"), value: waiting.method_label }]
            : []),
          {
            label: t("app.renew.sentLine"),
            value: formatDateTime(waiting.created_at, display),
          },
        ]}
      >
        {!wallet && (
          <Button
            variant="secondary"
            block
            disabled={pending}
            onClick={async () => {
              setPending(true);
              setError(null);
              try {
                await memberApi.withdraw(waiting.id);
                clear();
                mine.reload();
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setPending(false);
              }
            }}
          >
            {t("app.renew.withdraw")}
          </Button>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </StatusPanel>
    );
  }

  // The gym's latest answer.
  const answered = mine.data.requests.find(
    (r) => r.status === "approved" || r.status === "rejected",
  );
  const justRenewed =
    answered?.status === "approved" &&
    answered.reviewed_at !== null &&
    Date.parse(answered.reviewed_at) >= openedAt - 60_000 &&
    seen !== answered.id
      ? answered
      : null;
  if (justRenewed) {
    const done = () => {
      setSeen(justRenewed.id);
      clear();
    };
    return (
      <StatusPanel
        tone="done"
        title={t("app.renew.renewed")}
        lines={[
          { label: t("app.renew.planLine"), value: justRenewed.plan_name ?? "" },
          ...(state.valid_until
            ? [
                {
                  label: t("app.renew.untilLine"),
                  value: formatDate(state.valid_until, display),
                },
              ]
            : []),
          { label: t("app.renew.amountLine"), value: formatRs(justRenewed.amount) },
        ]}
      >
        <Link
          href={`/${slug}`}
          onClick={done}
          className="flex w-full items-center justify-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-brand hover:bg-brand-700"
        >
          {t("app.renew.showQr")}
        </Link>
        <Button variant="secondary" block onClick={done}>
          {t("app.renew.done")}
        </Button>
      </StatusPanel>
    );
  }

  // --- choosing and paying -------------------------------------------------------

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
  const online = Boolean(method?.online) && !byHand;
  const wallet = method ? t(`account.${method.kind}` as MessageKey) : "";
  const best = bestValue(plans);
  const rejected = answered?.status === "rejected" ? answered : null;

  async function payOnline() {
    if (!plan || !method) return;
    setPending(true);
    setError(null);
    try {
      const started = await memberApi.startOnlinePayment({
        plan_id: plan.id,
        payment_method_id: method.id,
      });
      // The wallet's page, then back to /pay/…/back, which asks the wallet.
      window.location.assign(started.pay_url);
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!plan || !method || online) return;
    // A transaction ID or a screenshot, before anything is sent.
    if (!ref.trim() && !screenshot) {
      setNeedProof(true);
      reveal(finishStep.current);
      return;
    }
    setPending(true);
    setError(null);
    try {
      const created = await memberApi.createRequest({
        plan_id: plan.id,
        payment_method_id: method.id,
        amount: total,
        transaction_ref: ref.trim() || null,
      });
      if (screenshot)
        await memberApi.uploadScreenshot(
          created.id,
          await shrinkImage(screenshot.file),
        );
      clear();
      mine.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  let next: React.ReactNode;
  if (!plan) {
    next = (
      <Button block disabled>
        {t("app.renew.chooseFirst")}
      </Button>
    );
  } else if (!method) {
    next = (
      <Button block disabled>
        {t("app.renew.chooseMethod")}
      </Button>
    );
  } else if (online) {
    next = (
      <Button block disabled={pending} onClick={() => void payOnline()}>
        {pending
          ? t("app.renew.opening", { wallet })
          : t("app.renew.payWithShort", { wallet })}
      </Button>
    );
  } else {
    next = (
      <Button type="submit" block disabled={pending}>
        {t("app.renew.sent")}
      </Button>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="space-y-6">
      <h1 className="text-xl font-bold tracking-tight text-slate-900">
        {t("app.renew.title")}
      </h1>

      {/* Where they stand, and when the new one would start. */}
      <div className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
              {t("app.renew.now")}
            </p>
            <p className="mt-1 font-semibold text-slate-900">
              {state.plan_name ?? t("app.home.status.none")}
            </p>
            {state.valid_until && (
              <p className="text-sm text-slate-600">
                {state.status === "expired"
                  ? t("app.renew.endedOn", {
                      date: formatDate(state.valid_until, display),
                    })
                  : t("app.renew.activeUntil", {
                      date: formatDate(state.valid_until, display),
                    })}
              </p>
            )}
          </div>
          {state.status === "active" && (
            <div className="shrink-0 text-center">
              <p
                className="text-2xl font-bold tabular-nums"
                style={{ color: me.gym.brand_color ?? undefined }}
              >
                {state.days_left}
              </p>
              <p className="text-xs text-slate-500">{t("app.home.daysLeft")}</p>
            </div>
          )}
        </div>
        <p className="mt-3 flex items-center gap-2 border-t border-hairline pt-3 text-sm text-slate-600">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-4.5 shrink-0 text-slate-400"
            aria-hidden
          >
            <path d="M8 3v3m8-3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z" />
          </svg>
          {t("app.renew.startsOn", {
            date: formatDate(options.data.renewal_starts_on, display),
          })}
        </p>
      </div>

      {rejected && (
        <Notice tone="warning">
          {t("app.renew.rejected", { reason: rejected.reject_reason ?? "" })}
        </Notice>
      )}

      <Step n={1} title={t("app.renew.choosePlan")} done={Boolean(plan)}>
        <div
          role="radiogroup"
          aria-label={t("app.renew.choosePlan")}
          className="space-y-2.5"
        >
          {plans.map((p) => (
            <PlanOption
              key={p.id}
              plan={p}
              checked={plan?.id === p.id}
              monthly={perMonth(p)}
              saved={savings(p, plans)}
              best={p.id === best}
              onChange={() => {
                if (!plan) reveal(payStep.current);
                setPlan(p);
              }}
            />
          ))}
        </div>
        {plan && (mates.length > 0 || admission > 0) && (
          <div className="space-y-2 rounded-2xl bg-surface p-3.5 text-sm ring-1 ring-hairline">
            {mates.length > 0 && (
              <p className="text-slate-600">
                {t("app.renew.forEveryone", {
                  names: mates.map((m) => m.name).join(", "),
                })}
              </p>
            )}
            <p className="flex justify-between">
              <span>{plan.name}</span>
              <Money paisa={plan.price} />
            </p>
            {admission > 0 && (
              <p className="flex justify-between">
                <span>{t("sale.admissionFee")}</span>
                <Money paisa={admission} />
              </p>
            )}
          </div>
        )}
      </Step>

      <div ref={payStep} className="scroll-mt-4">
        <Step
          n={2}
          title={t("app.renew.howToPay")}
          done={Boolean(method)}
          reached={Boolean(plan)}
        >
          {plan &&
            (methods.length === 0 ? (
              <Notice>{t("app.renew.noMethods")}</Notice>
            ) : (
              <div
                role="radiogroup"
                aria-label={t("app.renew.howToPay")}
                className="space-y-2.5"
              >
                {methods.map((m) => (
                  <MethodOption
                    key={m.id}
                    method={m}
                    checked={methodId === m.id}
                    onChange={() => {
                      if (!methodId) reveal(finishStep.current);
                      setMethodId(m.id);
                      setByHand(false);
                      setNeedProof(false);
                      setError(null);
                    }}
                  />
                ))}
              </div>
            ))}
        </Step>
      </div>

      <div ref={finishStep} className="scroll-mt-4">
        <Step
          n={3}
          title={
            online ? t("app.renew.step3Online", { wallet }) : t("app.renew.step3Qr")
          }
          done={false}
          reached={Boolean(method)}
        >
          {method && online && (
            <div className="space-y-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
              <div className="flex items-center gap-3">
                <WalletBadge kind={method.kind} size={44} />
                <p className="min-w-0 flex-1 text-sm text-slate-600">
                  {t("app.renew.securePay", { wallet, gym: me.gym.name })}
                </p>
              </div>
              {error && <Notice tone="error">{error}</Notice>}
              <button
                type="button"
                onClick={() => setByHand(true)}
                className="min-h-11 text-sm font-semibold text-brand-700 hover:text-brand-800"
              >
                {t("app.renew.orByHand")}
              </button>
            </div>
          )}

          {method && !online && (
            <>
              <div className="space-y-3 rounded-2xl bg-surface p-4 text-center shadow-card ring-1 ring-hairline">
                <h3 className="font-semibold text-slate-900">
                  {t("app.renew.payTitle", {
                    amount: formatRs(total),
                    name: method.account_name ?? me.gym.name,
                  })}
                </h3>
                {method.qr_image_url && (
                  <>
                    <div className="mx-auto w-fit rounded-2xl bg-white p-3 ring-1 ring-hairline">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={method.qr_image_url}
                        alt={method.label}
                        className="size-56 object-contain"
                      />
                    </div>
                    <Button
                      variant="secondary"
                      block
                      onClick={() =>
                        void saveQr(
                          method.qr_image_url!,
                          `${slug}-${method.kind}-qr.png`,
                        )
                      }
                    >
                      {t("pay.saveQr")}
                    </Button>
                  </>
                )}
                {method.account_number && (
                  <p className="font-medium text-slate-700 select-all">
                    {method.account_number}
                  </p>
                )}
                <p className="text-[0.8125rem] text-slate-500">
                  {t("app.renew.qrSteps", { amount: formatRs(total) })}
                </p>
              </div>

              <div className="space-y-4 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
                <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
                  {t("app.renew.proof")}
                </p>
                <Field
                  label={t("payment.transactionRef")}
                  value={ref}
                  onChange={(value) => {
                    setRef(value);
                    setNeedProof(false);
                  }}
                  help={t("app.renew.refHelp")}
                  autoComplete="off"
                />
                <div className="space-y-2">
                  <p className="text-sm font-medium text-slate-700">
                    {t("app.renew.screenshot")}
                  </p>
                  {screenshot ? (
                    <div className="flex items-center gap-3">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={screenshot.url}
                        alt=""
                        className="h-24 w-14 rounded-lg object-cover ring-1 ring-hairline"
                      />
                      <p className="min-w-0 flex-1 text-sm">
                        {t("app.renew.screenshotAdded")}
                      </p>
                      <Button variant="ghost" onClick={() => pickScreenshot(null)}>
                        {t("app.renew.removeScreenshot")}
                      </Button>
                    </div>
                  ) : (
                    <label className="flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 text-sm text-slate-600 hover:border-slate-400 hover:bg-slate-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand-500">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="size-5"
                        aria-hidden
                      >
                        <path d="M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Zm-1 12 4.5-4.5L13 16m-1.5-1.5L14 12l6 6M15 8.5h.01" />
                      </svg>
                      {t("app.renew.pickScreenshot")}
                      <input
                        type="file"
                        accept="image/*"
                        className="sr-only"
                        onChange={(e) => {
                          pickScreenshot(e.target.files?.[0] ?? null);
                          e.target.value = "";
                        }}
                      />
                    </label>
                  )}
                </div>
                {needProof && <Notice tone="error">{t("app.renew.needProof")}</Notice>}
                {error && <Notice tone="error">{error}</Notice>}
              </div>
            </>
          )}
        </Step>
      </div>

      <CheckoutBar
        total={plan ? total : null}
        caption={plan ? plan.name : t("app.renew.total")}
      >
        {next}
      </CheckoutBar>
    </form>
  );
}
