"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Checkbox, MoneyInput } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { adminApi, errorMessage, type PlatformPlan } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

/** Our prices. They live here, never in the code (PLAN.md §5.7, §15). */
export default function AdminPlansPage() {
  const { data, reload } = useLoad(() => adminApi.plans(), []);
  return (
    <div className="space-y-4">
      <PageHeader title={t("admin.plans")} subtitle={t("admin.plansHelp")} />
      {data?.map((plan) => (
        <PlanEditor key={plan.id} plan={plan} onSaved={reload} />
      ))}
      <PlanEditor plan={null} onSaved={reload} />
    </div>
  );
}

function PlanEditor({
  plan,
  onSaved,
}: {
  plan: PlatformPlan | null;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: plan?.name ?? "",
    max_active_members: plan?.max_active_members?.toString() ?? "",
    max_branches: plan?.max_branches?.toString() ?? "",
    monthly_price: plan?.monthly_price ?? null,
    included_sms: plan?.included_sms?.toString() ?? "0",
    is_active: plan?.is_active ?? true,
  });
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const number = (value: string) => (value.trim() === "" ? null : Number(value));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      name: form.name,
      max_active_members: number(form.max_active_members),
      max_branches: number(form.max_branches),
      monthly_price: form.monthly_price,
      included_sms: Number(form.included_sms || 0),
      is_active: form.is_active,
    };
    try {
      if (plan) await adminApi.updatePlan(plan.id, body);
      else await adminApi.createPlan(body);
      setMessage({ tone: "success", text: t("common.saved") });
      onSaved();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={plan ? plan.name : t("admin.newPlan")}>
      <form onSubmit={(e) => void save(e)} className="grid gap-3 sm:grid-cols-3">
        <Field
          label={t("plans.name")}
          value={form.name}
          onChange={(name) => setForm({ ...form, name })}
          required
        />
        <MoneyInput
          label={t("admin.monthlyPrice")}
          value={form.monthly_price}
          onChange={(monthly_price) => setForm({ ...form, monthly_price })}
        />
        <Field
          label={t("admin.includedSms")}
          value={form.included_sms}
          onChange={(included_sms) => setForm({ ...form, included_sms })}
          type="number"
        />
        <Field
          label={t("admin.maxMembers")}
          value={form.max_active_members}
          onChange={(max_active_members) => setForm({ ...form, max_active_members })}
          type="number"
          help={t("admin.blankNoLimit")}
        />
        <Field
          label={t("admin.maxBranches")}
          value={form.max_branches}
          onChange={(max_branches) => setForm({ ...form, max_branches })}
          type="number"
          help={t("admin.blankNoLimit")}
        />
        <div className="flex items-end">
          <Checkbox
            label={t("plans.offered")}
            checked={form.is_active}
            onChange={(is_active) => setForm({ ...form, is_active })}
          />
        </div>
        <div className="sm:col-span-3">
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          <Button type="submit" className="mt-2">
            {plan ? t("common.save") : t("common.add")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
