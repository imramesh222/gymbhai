"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, MoneyInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { plural, t } from "@/i18n";
import { errorMessage, ptApi, type PtKind, type PtPlan } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

/** "12 sessions · 2 months", "Monthly · 1 month". */
export function ptPlanTerms(plan: {
  kind: PtKind;
  sessions: number | null;
  duration_months: number | null;
  duration_days: number | null;
}): string {
  const kind =
    plan.kind === "sessions"
      ? plural(
          plan.sessions ?? 0,
          "pt.plans.sessionsCount.one",
          "pt.plans.sessionsCount.other",
        )
      : t("pt.kind.monthly");
  const length = plan.duration_months
    ? plural(plan.duration_months, "plans.months.one", "plans.months.other")
    : plural(plan.duration_days ?? 0, "plans.days.one", "plans.days.other");
  return `${kind} · ${length}`;
}

/** Settings → Personal training: the gym's own PT plans (PLAN.md §18.3). */
export function PtPlansSection() {
  const { data, error, reload } = useLoad(() => ptApi.plans(true), []);
  const [editing, setEditing] = useState<PtPlan | "new" | null>(null);
  return (
    <Card
      title={t("pt.plans.title")}
      actions={<Button onClick={() => setEditing("new")}>{t("pt.plans.add")}</Button>}
    >
      <p className="mb-2 text-sm text-slate-600">{t("pt.plans.help")}</p>
      {error && <Notice tone="error">{error}</Notice>}
      {data && data.length === 0 && <EmptyState title={t("pt.plans.none")} />}
      <ul className="divide-y divide-hairline">
        {(data ?? []).map((plan) => (
          <li key={plan.id}>
            <button
              type="button"
              onClick={() => setEditing(plan)}
              className="flex w-full items-center justify-between gap-3 py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className={plan.is_active ? "" : "text-slate-500"}>
                <span className="font-medium">{plan.name}</span>
                <span className="text-slate-500"> · {ptPlanTerms(plan)}</span>
                {!plan.is_active && <span> · {t("plans.hidden")}</span>}
              </span>
              <Money paisa={plan.price} className="font-semibold" />
            </button>
          </li>
        ))}
      </ul>
      {editing && (
        <PtPlanDialog
          plan={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

function PtPlanDialog({
  plan,
  onClose,
  onSaved,
}: {
  plan: PtPlan | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: plan?.name ?? "",
    kind: plan?.kind ?? ("sessions" as PtKind),
    sessions: String(plan?.sessions ?? 12),
    unit: (plan?.duration_days ? "days" : "months") as "months" | "days",
    length: String(plan?.duration_months ?? plan?.duration_days ?? 1),
    price: plan?.price ?? null,
    is_active: plan?.is_active ?? true,
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const length = Number(form.length);
    const body = {
      name: form.name,
      kind: form.kind,
      sessions: form.kind === "sessions" ? Number(form.sessions) : null,
      duration_months: form.unit === "months" ? length : null,
      duration_days: form.unit === "days" ? length : null,
      price: form.price ?? 0,
      ...(plan ? { is_active: form.is_active } : {}),
    };
    setPending(true);
    setError(null);
    try {
      if (plan) await ptApi.updatePlan(plan.id, body);
      else await ptApi.createPlan(body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={plan ? t("pt.plans.edit") : t("pt.plans.add")}
    >
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <Field
          label={t("plans.name")}
          value={form.name}
          onChange={(name) => setForm({ ...form, name })}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Select<PtKind>
            label={t("pt.plans.kind")}
            value={form.kind}
            onChange={(kind) => setForm({ ...form, kind })}
            options={[
              { value: "sessions", label: t("pt.kind.sessions") },
              { value: "monthly", label: t("pt.kind.monthly") },
            ]}
          />
          {form.kind === "sessions" && (
            <Field
              label={t("pt.plans.sessions")}
              value={form.sessions}
              onChange={(sessions) => setForm({ ...form, sessions })}
              type="number"
              inputMode="numeric"
              required
            />
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field
            label={t("plans.length")}
            value={form.length}
            onChange={(length) => setForm({ ...form, length })}
            type="number"
            inputMode="numeric"
            required
            help={form.kind === "sessions" ? t("pt.plans.lengthHelp") : undefined}
          />
          <Select<"months" | "days">
            label={t("plans.unit")}
            value={form.unit}
            onChange={(unit) => setForm({ ...form, unit })}
            options={[
              { value: "months", label: t("plans.unit.months") },
              { value: "days", label: t("plans.unit.days") },
            ]}
          />
        </div>
        <MoneyInput
          label={t("sale.price")}
          value={form.price}
          onChange={(price) => setForm({ ...form, price })}
          required
        />
        {plan && (
          <Checkbox
            label={t("plans.offered")}
            checked={form.is_active}
            onChange={(is_active) => setForm({ ...form, is_active })}
          />
        )}
        <p className="text-xs text-slate-500">{t("pt.plans.changeHelp")}</p>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {pending ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
