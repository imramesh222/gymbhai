"use client";

import { MoneyInput, Select } from "@/components/ui/inputs";
import { Field } from "@/components/Field";
import { t, type MessageKey } from "@/i18n";
import type { Method } from "@/lib/api";

export const METHODS: Method[] = ["cash", "esewa", "khalti", "fonepay", "bank"];

export function methodLabel(method: string): string {
  return t(`method.${method}` as MessageKey);
}

export interface PaymentDraft {
  amount: number | null;
  method: Method;
  transactionRef: string;
}

/** Amount, method and transaction ID for money received now. */
export function PaymentFields({
  value,
  onChange,
  owed,
  amountLabel,
}: {
  value: PaymentDraft;
  onChange: (value: PaymentDraft) => void;
  owed?: number;
  amountLabel?: string;
}) {
  return (
    <div className="space-y-3">
      {owed !== undefined && owed > 0 && (
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["payment.full", owed],
              ["payment.nothing", null],
            ] as [MessageKey, number | null][]
          ).map(([key, amount]) => (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ ...value, amount })}
              className={`rounded-full border px-3 py-1 text-sm ${
                value.amount === amount
                  ? "border-brand-600 bg-brand-50 text-brand-900"
                  : "border-slate-300 text-slate-700"
              }`}
            >
              {t(key)}
            </button>
          ))}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <MoneyInput
          label={amountLabel ?? t("payment.amount")}
          value={value.amount}
          onChange={(amount) => onChange({ ...value, amount })}
          help={
            owed !== undefined && value.amount !== null && value.amount < owed
              ? t("payment.partHelp")
              : undefined
          }
        />
        <Select<Method>
          label={t("payment.method")}
          value={value.method}
          onChange={(method) => onChange({ ...value, method })}
          options={METHODS.map((m) => ({ value: m, label: methodLabel(m) }))}
        />
      </div>
      {value.method !== "cash" && (
        <Field
          label={t("payment.transactionRef")}
          value={value.transactionRef}
          onChange={(transactionRef) => onChange({ ...value, transactionRef })}
          help={t("payment.transactionRefHelp")}
        />
      )}
    </div>
  );
}

export function toPaymentInput(draft: PaymentDraft) {
  if (!draft.amount) return null;
  return {
    amount: draft.amount,
    method: draft.method,
    transaction_ref: draft.transactionRef.trim() || null,
  };
}
