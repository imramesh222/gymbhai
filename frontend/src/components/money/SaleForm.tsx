"use client";

import { useState } from "react";

import { Money } from "@/components/ui/Money";
import { DateInput, MoneyInput, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import type { Picked } from "@/components/member/MemberPicker";
import type { Branch, Plan, SaleInput } from "@/lib/api";
import { planEnd, type Calendar, type DateDisplay } from "@/lib/dates";
import { formatRs } from "@/lib/money";

import { GroupPeople } from "./GroupPeople";
import { PaymentFields, toPaymentInput, type PaymentDraft } from "./PaymentFields";

export interface SaleDraft {
  planId: string;
  branchId: string;
  startDate: string;
  endDate: string;
  endEdited: boolean;
  price: number | null;
  discount: number | null;
  admissionFee: number | null;
  payment: PaymentDraft;
  /** A family or couple plan's others (§19.1). */
  withMembers: Picked[];
}

export function emptySale(startDate: string, branchId: string): SaleDraft {
  return {
    planId: "",
    branchId,
    startDate,
    endDate: "",
    endEdited: false,
    price: null,
    discount: 0,
    admissionFee: 0,
    payment: { amount: null, method: "cash", transactionRef: "" },
    withMembers: [],
  };
}

export function saleTotal(draft: SaleDraft): number {
  return (draft.price ?? 0) - (draft.discount ?? 0) + (draft.admissionFee ?? 0);
}

export function toSaleInput(draft: SaleDraft): SaleInput {
  return {
    plan_id: draft.planId,
    branch_id: draft.branchId || null,
    start_date: draft.startDate,
    end_date: draft.endDate,
    price: draft.price,
    discount: draft.discount ?? 0,
    admission_fee: draft.admissionFee ?? 0,
    payment: toPaymentInput(draft.payment),
    with_member_ids: draft.withMembers.map((p) => p.id),
  };
}

/**
 * Plan -> dates -> price -> payment (PLAN.md §5.3). The end date fills in from
 * the plan in the gym's own month counting; staff can change either date.
 */
export function SaleForm({
  plans,
  branches,
  value,
  onChange,
  calendar,
  display,
  firstMembership,
  payer,
}: {
  plans: Plan[];
  branches: Branch[];
  value: SaleDraft;
  onChange: (value: SaleDraft) => void;
  calendar: Calendar;
  display: DateDisplay;
  firstMembership: boolean;
  /** Who it's sold to: they pay for a family or couple plan (§19.1). */
  payer?: { id?: string; name?: string; phone?: string };
}) {
  const [paymentTouched, setPaymentTouched] = useState(false);
  const plan = plans.find((p) => p.id === value.planId);
  const availablePlans = plans.filter(
    (p) => p.all_branches || !value.branchId || p.branch_ids.includes(value.branchId),
  );

  function update(patch: Partial<SaleDraft>) {
    const next = { ...value, ...patch };
    const chosen = plans.find((p) => p.id === next.planId);
    if (chosen && next.startDate && !next.endEdited) {
      next.endDate = planEnd(next.startDate, chosen, calendar);
    }
    // Until staff type an amount, "paid now" follows the total.
    if (!paymentTouched)
      next.payment = { ...next.payment, amount: saleTotal(next) || null };
    onChange(next);
  }

  /** The plan's fee for each person on their first membership (§19.1). */
  function admissionFor(chosen: Plan | undefined, people: Picked[]): number {
    const newcomers = (firstMembership ? 1 : 0) + people.filter((p) => p.first).length;
    return (chosen?.admission_fee ?? 0) * newcomers;
  }

  function choosePlan(planId: string) {
    const chosen = plans.find((p) => p.id === planId);
    const people =
      (chosen?.seats ?? 1) > 1 ? value.withMembers.slice(0, chosen!.seats - 1) : [];
    update({
      planId,
      price: chosen?.price ?? null,
      admissionFee: admissionFor(chosen, people),
      endEdited: false,
      withMembers: people,
    });
  }

  function choosePeople(withMembers: Picked[]) {
    update({ withMembers, admissionFee: admissionFor(plan, withMembers) });
  }

  const total = saleTotal(value);
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          label={t("sale.plan")}
          value={value.planId}
          onChange={choosePlan}
          required
          options={availablePlans.map((p) => ({
            value: p.id,
            label: `${p.name} — ${p.price === null ? t("sale.noPrice") : formatRs(p.price)}`,
          }))}
        />
        {branches.length > 1 && (
          <Select
            label={t("sale.branch")}
            value={value.branchId}
            onChange={(branchId) => update({ branchId })}
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        )}
      </div>

      {plan && plan.seats > 1 && (
        <GroupPeople
          seats={plan.seats}
          value={value.withMembers}
          onChange={choosePeople}
          payerId={payer?.id}
          payerName={payer?.name}
          defaultPhone={payer?.phone}
          branchId={value.branchId}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <DateInput
          label={t("sale.start")}
          value={value.startDate}
          onChange={(startDate) => update({ startDate })}
          display={display}
          required
        />
        <DateInput
          label={t("sale.end")}
          value={value.endDate}
          onChange={(endDate) => update({ endDate, endEdited: true })}
          display={display}
          required
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MoneyInput
          label={t("sale.price")}
          value={value.price}
          onChange={(price) => update({ price })}
          required
          help={plan && plan.price === null ? t("sale.noPriceHelp") : undefined}
        />
        <MoneyInput
          label={t("sale.discount")}
          value={value.discount}
          onChange={(discount) => update({ discount })}
        />
        <MoneyInput
          label={t("sale.admissionFee")}
          value={value.admissionFee}
          onChange={(admissionFee) => update({ admissionFee })}
          help={
            plan && plan.seats > 1
              ? t("sale.admissionPeople")
              : firstMembership
                ? t("sale.admissionFirst")
                : t("sale.admissionRenewal")
          }
        />
      </div>

      <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
        <span className="text-sm text-slate-600">{t("sale.total")}</span>
        <Money paisa={total} className="text-lg font-semibold" />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-800">
          {t("sale.paidNow")}
        </h3>
        <PaymentFields
          value={value.payment}
          owed={total}
          onChange={(payment) => {
            setPaymentTouched(true);
            onChange({ ...value, payment });
          }}
        />
        {value.payment.amount !== null && value.payment.amount < total && (
          <p className="mt-2 text-sm text-amber-800">
            {t("sale.duesLeft", { amount: formatRs(total - value.payment.amount) })}
          </p>
        )}
      </div>
    </div>
  );
}
