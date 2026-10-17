"use client";

import { CircleCheck, Circle } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/Button";
import { Card } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, gymApi, type SetupChecklist as Steps } from "@/lib/api";

export const STEPS: { key: keyof Steps; label: MessageKey; href: string }[] = [
  { key: "plans_priced", label: "setup.plansPriced", href: "/staff/settings/plans" },
  {
    key: "payment_account",
    label: "setup.paymentAccount",
    href: "/staff/settings/payment-accounts",
  },
  { key: "first_member", label: "setup.firstMember", href: "/staff/members/new" },
  { key: "poster_printed", label: "setup.poster", href: "/staff/settings/poster" },
  { key: "logo", label: "setup.logo", href: "/staff/settings" },
  { key: "staff_invited", label: "setup.staff", href: "/staff/team" },
];

/**
 * A new gym's first steps (PLAN.md §16.2, 7.4), until they are done or put
 * away. Gyms that finish setting up in the trial are the ones that stay.
 */
export function SetupChecklist({
  steps,
  onDismissed,
}: {
  steps: Steps;
  onDismissed: () => void;
}) {
  const toast = useToast();
  const done = STEPS.filter((step) => steps[step.key]).length;
  return (
    <Card
      title={t("setup.title")}
      actions={
        <Button
          variant="ghost"
          size="sm"
          onClick={async () => {
            try {
              await gymApi.update({ settings: { setup_dismissed: true } });
              onDismissed();
            } catch (err) {
              toast.error(errorMessage(err));
            }
          }}
        >
          {t("setup.hide")}
        </Button>
      }
    >
      <p className="text-sm text-slate-600">
        {t("setup.progress", { done, total: STEPS.length })}
      </p>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={STEPS.length}
        aria-valuenow={done}
        aria-label={t("setup.title")}
      >
        <div
          className="h-full rounded-full bg-brand-600 transition-[width]"
          style={{ width: `${(done / STEPS.length) * 100}%` }}
        />
      </div>
      <ul className="mt-4 grid gap-1 sm:grid-cols-2">
        {STEPS.map((step) => {
          const ok = steps[step.key];
          const Icon = ok ? CircleCheck : Circle;
          return (
            <li key={step.key}>
              <Link
                href={step.href}
                className={`flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition hover:bg-slate-50 ${
                  ok ? "text-slate-500 line-through" : "font-medium text-slate-800"
                }`}
              >
                <Icon
                  className={`size-4 shrink-0 ${ok ? "text-emerald-600" : "text-slate-300"}`}
                  aria-hidden
                />
                {t(step.label)}
                <span className="sr-only">
                  {ok ? t("setup.done") : t("setup.todo")}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
