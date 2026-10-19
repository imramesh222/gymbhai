"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import {
  PaymentFields,
  toPaymentInput,
  type PaymentDraft,
} from "@/components/money/PaymentFields";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, MoneyInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import {
  errorMessage,
  ptApi,
  type Branch,
  type PtPackageDetail,
  type PtPlan,
  type Trainer,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { planEnd, todayInNepal, type Calendar, type DateDisplay } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useIdempotencyKey } from "@/lib/idempotency";
import { formatRs } from "@/lib/money";
import { useLoad } from "@/lib/useLoad";

import { ptPlanTerms } from "./PtPlansSection";

/**
 * Sell personal training (PLAN.md §18.3): a PT plan, a trainer, the dates (the
 * end from the plan's length in the gym's calendar), price and discount, and
 * the payment taken now if any. Saved once, however often it's tapped.
 */
export function SellTraining({
  memberId,
  homeBranchId,
  branches,
  onClose,
  onSold,
}: {
  memberId: string;
  homeBranchId: string;
  branches: Branch[];
  onClose: () => void;
  onSold: (sold: PtPackageDetail) => void;
}) {
  const { can, me } = useAuth();
  const { calendar, display } = useGymCalendar();
  const options = useLoad(() => Promise.all([ptApi.plans(), ptApi.trainers()]), []);
  const [plans, trainers] = options.data ?? [[], []];
  const collects = can("payments.collect");

  if (options.error) return <SellDialog onClose={onClose} error={options.error} />;
  if (!options.data) return <SellDialog onClose={onClose} />;
  if (plans.length === 0 || trainers.length === 0)
    return (
      <SellDialog onClose={onClose}>
        <p className="text-sm text-slate-600">
          {plans.length === 0 ? t("pt.noPlans") : t("pt.noTrainers")}
        </p>
      </SellDialog>
    );
  return (
    <SellForm
      memberId={memberId}
      branchId={homeBranchId}
      branches={branches}
      plans={plans}
      trainers={trainers}
      // A trainer selling to their own new client starts with themselves.
      firstTrainer={trainers.find((tr) => tr.id === me?.staff.id)?.id ?? ""}
      calendar={calendar}
      display={display}
      collects={collects}
      onClose={onClose}
      onSold={onSold}
    />
  );
}

function SellDialog({
  onClose,
  error,
  children,
}: {
  onClose: () => void;
  error?: string;
  children?: React.ReactNode;
}) {
  return (
    <Dialog open onClose={onClose} title={t("pt.sell")}>
      {error ? <Notice tone="error">{error}</Notice> : children}
      {!error && !children && (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      )}
    </Dialog>
  );
}

function SellForm({
  memberId,
  branchId: homeBranchId,
  branches,
  plans,
  trainers,
  firstTrainer,
  calendar,
  display,
  collects,
  onClose,
  onSold,
}: {
  memberId: string;
  branchId: string;
  branches: Branch[];
  plans: PtPlan[];
  trainers: Trainer[];
  firstTrainer: string;
  calendar: Calendar;
  display: DateDisplay;
  collects: boolean;
  onClose: () => void;
  onSold: (sold: PtPackageDetail) => void;
}) {
  const [planId, setPlanId] = useState("");
  const [trainerId, setTrainerId] = useState(firstTrainer);
  const [branchId, setBranchId] = useState(homeBranchId);
  const [startDate, setStartDate] = useState(todayInNepal());
  const [endDate, setEndDate] = useState("");
  const [endEdited, setEndEdited] = useState(false);
  const [price, setPrice] = useState<number | null>(null);
  const [discount, setDiscount] = useState<number | null>(0);
  const [payment, setPayment] = useState<PaymentDraft>({
    amount: null,
    method: "cash",
    transactionRef: "",
  });
  const [paymentTouched, setPaymentTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const saving = useIdempotencyKey();

  const plan = plans.find((p) => p.id === planId);
  const total = (price ?? 0) - (discount ?? 0);

  // The end follows the plan and start until someone types one (a new plan
  // starts it again); "paid now" follows the total until someone types an
  // amount.
  function follow({
    plan: chosen = plan,
    start = startDate,
    price: newPrice = price,
    discount: newDiscount = discount,
    newPlan = false,
  }: {
    plan?: PtPlan;
    start?: string;
    price?: number | null;
    discount?: number | null;
    newPlan?: boolean;
  }) {
    if (chosen && start && (newPlan || !endEdited))
      setEndDate(planEnd(start, chosen, calendar));
    if (!paymentTouched) {
      const owed = (newPrice ?? 0) - (newDiscount ?? 0);
      setPayment({ ...payment, amount: owed > 0 ? owed : null });
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!plan || !trainerId) return;
    const body = {
      plan_id: plan.id,
      trainer_id: trainerId,
      branch_id: branchId || null,
      start_date: startDate,
      end_date: endDate,
      price,
      discount: discount ?? 0,
      payment: collects ? toPaymentInput(payment) : null,
    };
    setPending(true);
    setError(null);
    try {
      const sold = await ptApi.sell(memberId, body, saving.keyFor(body));
      saving.succeeded();
      onSold(sold.package);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("pt.sell")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label={t("pt.plan")}
            value={planId}
            required
            onChange={(id) => {
              const chosen = plans.find((p) => p.id === id);
              setPlanId(id);
              setPrice(chosen?.price ?? null);
              setEndEdited(false);
              follow({ plan: chosen, price: chosen?.price ?? null, newPlan: true });
            }}
            options={plans.map((p) => ({
              value: p.id,
              label: `${p.name} — ${formatRs(p.price)}`,
            }))}
          />
          <Select
            label={t("pt.trainer")}
            value={trainerId}
            required
            onChange={setTrainerId}
            options={trainers.map((tr) => ({ value: tr.id, label: tr.name }))}
          />
        </div>
        {plan && <p className="-mt-2 text-xs text-slate-500">{ptPlanTerms(plan)}</p>}
        {branches.length > 1 && (
          <Select
            label={t("sale.branch")}
            value={branchId}
            onChange={setBranchId}
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <DateInput
            label={t("sale.start")}
            value={startDate}
            onChange={(start) => {
              setStartDate(start);
              follow({ start });
            }}
            display={display}
            required
          />
          <DateInput
            label={t("sale.end")}
            value={endDate}
            onChange={(end) => {
              setEndDate(end);
              setEndEdited(true);
            }}
            display={display}
            required
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <MoneyInput
            label={t("sale.price")}
            value={price}
            onChange={(next) => {
              setPrice(next);
              follow({ price: next });
            }}
            required
          />
          <MoneyInput
            label={t("sale.discount")}
            value={discount}
            onChange={(next) => {
              setDiscount(next);
              follow({ discount: next });
            }}
          />
        </div>
        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
          <span className="text-sm text-slate-600">{t("sale.total")}</span>
          <Money paisa={total} className="text-lg font-semibold" />
        </div>
        {collects && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-800">
              {t("sale.paidNow")}
            </h3>
            <PaymentFields
              value={payment}
              owed={total}
              onChange={(next) => {
                setPaymentTouched(true);
                setPayment(next);
              }}
            />
            {payment.amount !== null && payment.amount < total && (
              <p className="mt-2 text-sm text-amber-800">
                {t("sale.duesLeft", { amount: formatRs(total - payment.amount) })}
              </p>
            )}
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending || !plan || !trainerId}>
          {pending ? t("common.saving") : t("pt.sell")}
        </Button>
      </form>
    </Dialog>
  );
}
