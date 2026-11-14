"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
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
      {/* New plan first: adding one never means scrolling past every plan, and
          the form stays put while the list loads and grows below it. */}
      <MessagePrices />
      <AppPrices />
      <PlanEditor plan={null} onSaved={reload} />
      {!data ? (
        <PageSkeleton label={t("common.loading")} />
      ) : (
        data.map((plan) => <PlanEditor key={plan.id} plan={plan} onSaved={reload} />)
      )}
    </div>
  );
}

/** What a WhatsApp message costs a gym, in message credits (§19.3). */
function MessagePrices() {
  const { data, setData } = useLoad(() => adminApi.settings(), []);
  const [credits, setCredits] = useState<string | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  if (!data) return null;
  const value = credits ?? String(data.whatsapp_credits);
  return (
    <Card title={t("admin.messagePrices")}>
      <Form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            setData(await adminApi.updateSettings({ whatsapp_credits: Number(value) }));
            setCredits(null);
            setMessage({ tone: "success", text: t("common.saved") });
          } catch (err) {
            setMessage({ tone: "error", text: errorMessage(err) });
          }
        }}
      >
        <p className="text-sm text-slate-600">{t("admin.messagePricesHelp")}</p>
        <div className="max-w-56">
          <Field
            label={t("admin.whatsappCredits")}
            value={value}
            onChange={setCredits}
            type="number"
            inputMode="numeric"
          />
        </div>
        {!data.whatsapp_available && (
          <Notice tone="warning">{t("admin.whatsappNotSetUp")}</Notice>
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit" variant="secondary">
          {t("common.save")}
        </Button>
      </Form>
    </Card>
  );
}

/** What a gym's own app in the stores costs it (§20.3). */
function AppPrices() {
  const { data, setData } = useLoad(() => adminApi.settings(), []);
  const [prices, setPrices] = useState<{
    setup: number | null;
    monthly: number | null;
  } | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  if (!data) return null;
  const shown = prices ?? {
    setup: data.branded_app_setup_price,
    monthly: data.branded_app_monthly_price,
  };
  return (
    <Card title={t("admin.appPrices")}>
      <Form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            setData(
              await adminApi.updateSettings({
                branded_app_setup_price: shown.setup,
                branded_app_monthly_price: shown.monthly,
              }),
            );
            setPrices(null);
            setMessage({ tone: "success", text: t("common.saved") });
          } catch (err) {
            setMessage({ tone: "error", text: errorMessage(err) });
          }
        }}
      >
        <p className="text-sm text-slate-600">{t("admin.appPricesHelp")}</p>
        <div className="grid max-w-md grid-cols-2 gap-3">
          <MoneyInput
            label={t("admin.appSetupPrice")}
            value={shown.setup}
            onChange={(setup) => setPrices({ ...shown, setup })}
          />
          <MoneyInput
            label={t("admin.appMonthlyPrice")}
            value={shown.monthly}
            onChange={(monthly) => setPrices({ ...shown, monthly })}
          />
        </div>
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit" variant="secondary">
          {t("common.save")}
        </Button>
      </Form>
    </Card>
  );
}

function PlanEditor({
  plan,
  onSaved,
}: {
  plan: PlatformPlan | null;
  onSaved: () => void;
}) {
  const blank = () => ({
    name: plan?.name ?? "",
    max_active_members: plan?.max_active_members?.toString() ?? "",
    max_branches: plan?.max_branches?.toString() ?? "",
    monthly_price: plan?.monthly_price ?? null,
    included_sms: plan?.included_sms?.toString() ?? "0",
    is_active: plan?.is_active ?? true,
  });
  const [form, setForm] = useState(blank);
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
      else {
        await adminApi.createPlan(body);
        setForm(blank()); // ready for the next one, not the same one twice
      }
      setMessage({ tone: "success", text: t("common.saved") });
      onSaved();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={plan ? plan.name : t("admin.newPlan")}>
      <Form onSubmit={save} className="grid gap-3 sm:grid-cols-3">
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
      </Form>
    </Card>
  );
}
