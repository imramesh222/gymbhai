"use client";

import Link from "next/link";

import { DeskSms, HowMessagesGo } from "@/components/automations/DeskSms";
import { TriggerCard } from "@/components/automations/Automations";
import { TRIGGERS } from "@/components/automations/triggers";
import { Notice } from "@/components/Notice";
import { PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { t } from "@/i18n";
import { messagesApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/useLoad";

/**
 * Messages → Automations (PLAN.md §16.3, 8.2): the SMS GymBhai sends for the
 * gym every morning, one card per trigger, and the wording of the desk SMS.
 */
export default function AutomationsPage() {
  const { can } = useAuth();
  const rules = useLoad(() => messagesApi.rules(), []);
  const templates = useLoad(() => messagesApi.templates(), []);
  const error = rules.error || templates.error;

  return (
    <div className="space-y-4">
      <PageHeader title={t("automations.title")} subtitle={t("automations.subtitle")} />
      {can("messages.sms") && (
        <p className="text-sm text-slate-600">
          {t("automations.credits")}{" "}
          <Link
            href="/staff/sms"
            className="font-medium text-brand-700 hover:underline"
          >
            {t("automations.seeSent")}
          </Link>
        </p>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {templates.data && <HowMessagesGo initial={templates.data.also_sms} />}
      {!rules.data && !error && <PageSkeleton label={t("common.loading")} />}
      {rules.data &&
        (["membership", "pt", "progress"] as const).map((group) => (
          <div key={group} className="space-y-3">
            {group !== "membership" && (
              <h2 className="pt-2 text-[0.9375rem] font-semibold text-slate-900">
                {t(group === "pt" ? "pt.title" : "progress.title")}
              </h2>
            )}
            <div className="grid gap-4 lg:grid-cols-2">
              {TRIGGERS.filter((info) => info.group === group).map((info) => (
                <TriggerCard
                  key={info.trigger}
                  info={info}
                  rules={rules
                    .data!.filter((r) => r.trigger === info.trigger)
                    .sort((a, b) => a.days - b.days)}
                  onChanged={rules.reload}
                />
              ))}
            </div>
          </div>
        ))}
      {templates.data && <DeskSms initial={templates.data} />}
    </div>
  );
}
