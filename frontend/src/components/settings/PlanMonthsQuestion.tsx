"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Choice } from "@/components/Choice";
import { Notice } from "@/components/Notice";
import { t } from "@/i18n";
import { errorMessage, gymApi, type PlanMonths } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * How the gym counts plan months, asked once before anything counted in
 * months is sold (PLAN.md §5.1): on Plans, and in place of a sale form. No
 * form element: it sits inside the sale forms. Staff who can't change the
 * gym's settings are told to ask the owner.
 */
export function PlanMonthsQuestion() {
  const { can, refreshMe } = useAuth();
  const [choice, setChoice] = useState<PlanMonths | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!can("setup.gym"))
    return <Notice tone="warning">{t("planMonths.askOwner")}</Notice>;

  async function save() {
    if (!choice) return;
    setPending(true);
    setError(null);
    try {
      await gymApi.update({ settings: { plan_months: choice } });
      // The question goes away once the gym has the answer.
      await refreshMe();
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl bg-brand-50 p-4 ring-1 ring-brand-200/70 sm:p-5">
      <Choice<PlanMonths>
        legend={t("planMonths.title")}
        name="plan_months"
        value={choice}
        onChange={setChoice}
        options={[
          {
            value: "bs",
            label: t("signup.planMonths.bs"),
            hint: t("signup.planMonths.bsExample"),
          },
          {
            value: "ad",
            label: t("signup.planMonths.ad"),
            hint: t("signup.planMonths.adExample"),
          },
        ]}
      />
      <p className="text-sm text-slate-600">
        {t("planMonths.intro")} {t("planMonths.later")}
      </p>
      {error && <Notice tone="error">{error}</Notice>}
      <Button onClick={() => save()} disabled={!choice || pending}>
        {t("common.save")}
      </Button>
    </div>
  );
}
