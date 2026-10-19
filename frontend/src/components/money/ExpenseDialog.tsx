"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { methodLabel, METHODS } from "@/components/money/PaymentFields";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, MoneyInput, Select, TextArea } from "@/components/ui/inputs";
import { isMessageKey, t } from "@/i18n";
import {
  EXPENSE_CATEGORIES,
  errorMessage,
  type Branch,
  type Expense,
  type ExpenseCategory,
  type ExpenseInput,
  type Method,
} from "@/lib/api";
import { todayInNepal, type DateDisplay } from "@/lib/dates";

export function categoryLabel(category: string): string {
  const key = `expenses.category.${category}`;
  return isMessageKey(key) ? t(key) : category;
}

/** The select's value for "the whole gym", which the API calls no branch. */
const WHOLE_GYM = "whole-gym";

/**
 * Add an expense, add one like another ("Same again": rent and salaries come
 * every month), or correct one (PLAN.md §18.1).
 */
export function ExpenseDialog({
  title,
  from,
  editing = false,
  branches,
  wholeGym,
  display,
  onClose,
  onSave,
}: {
  title: string;
  /** Filled in from this one: the expense being edited, or repeated. */
  from?: Expense | null;
  editing?: boolean;
  /** The branches this person works at. */
  branches: Branch[];
  /** They work at every branch, so may record the whole gym's. */
  wholeGym: boolean;
  display: DateDisplay;
  onClose: () => void;
  onSave: (body: ExpenseInput, reason: string | null) => Promise<void>;
}) {
  const open = branches.filter((b) => b.is_active || b.id === from?.branch_id);
  const [category, setCategory] = useState<ExpenseCategory | "">(from?.category ?? "");
  const [amount, setAmount] = useState<number | null>(from?.amount ?? null);
  const [spentOn, setSpentOn] = useState(
    editing && from ? from.spent_on : todayInNepal(),
  );
  const [method, setMethod] = useState<Method>(from?.method ?? "cash");
  const [paidTo, setPaidTo] = useState(from?.paid_to ?? "");
  const [note, setNote] = useState(from?.note ?? "");
  const [branch, setBranch] = useState(
    from
      ? (from.branch_id ?? WHOLE_GYM)
      : wholeGym
        ? WHOLE_GYM
        : (open[0]?.id ?? WHOLE_GYM),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // A ref, not state: a second tap in the same frame must find it taken.
  const busy = useRef(false);

  const choices = [
    ...(wholeGym ? [{ value: WHOLE_GYM, label: t("expenses.wholeGym") }] : []),
    ...open.map((b) => ({ value: b.id, label: b.name })),
  ];
  // One branch: nothing to choose.
  const showBranch = open.length > 1;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current || !category || !amount) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    try {
      await onSave(
        {
          category,
          amount,
          spent_on: spentOn,
          method,
          paid_to: paidTo.trim() || null,
          note: note.trim() || null,
          branch_id: branch === WHOLE_GYM ? null : branch,
        },
        reason.trim() || null,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={title}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Select<ExpenseCategory>
            label={t("expenses.category")}
            value={category}
            onChange={setCategory}
            required
            options={EXPENSE_CATEGORIES.map((c) => ({
              value: c,
              label: categoryLabel(c),
            }))}
          />
          <MoneyInput
            label={t("payment.amount")}
            value={amount}
            onChange={setAmount}
            required
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <DateInput
            label={t("expenses.date")}
            value={spentOn}
            onChange={setSpentOn}
            display={display}
            required
          />
          <Select<Method>
            label={t("payment.method")}
            value={method}
            onChange={setMethod}
            options={METHODS.map((m) => ({ value: m, label: methodLabel(m) }))}
          />
        </div>
        <Field
          label={t("expenses.paidTo")}
          value={paidTo}
          onChange={setPaidTo}
          optional
          optionalLabel={t("common.optional")}
          help={t("expenses.paidToHelp")}
        />
        {showBranch && (
          <Select
            label={t("expenses.branch")}
            value={branch}
            onChange={setBranch}
            options={choices}
          />
        )}
        <TextArea label={t("expenses.note")} value={note} onChange={setNote} />
        {editing && (
          <Field
            label={t("expenses.reason")}
            value={reason}
            onChange={setReason}
            optional
            optionalLabel={t("common.optional")}
          />
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={saving || !category || !amount}>
          {saving ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
