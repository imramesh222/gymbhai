"use client";

import { Card, Stat } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { adminApi } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

const STATES = ["trial", "paying", "grace", "read_only", "suspended"] as const;

/** How we're doing (PLAN.md §16.5, 10.1). */
export function AdminSummary() {
  const { data } = useLoad(() => adminApi.summary(), []);
  if (!data) return null;
  const conversion =
    data.trial_conversion === null
      ? "—"
      : `${Math.round(data.trial_conversion * 100)}%`;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat value={<Money paisa={data.mrr} />} label={t("admin.mrr")} />
        <Stat value={data.gyms} label={t("admin.gymsTotal")} />
        <Stat
          value={conversion}
          label={t("admin.trialConversion", {
            converted: data.trials_converted,
            ended: data.trials_ended,
          })}
        />
        <Stat
          value={data.going_quiet}
          label={t("admin.goingQuiet")}
          tone={data.going_quiet ? "warning" : "plain"}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={t("admin.byState")}>
          <dl className="divide-y divide-hairline text-sm">
            {STATES.map((s) => (
              <div key={s} className="flex justify-between py-1.5">
                <dt>{t(`admin.state.${s}` as MessageKey)}</dt>
                <dd className="font-semibold tabular-nums">{data.by_state[s]}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title={t("admin.lost")}>
          <dl className="divide-y divide-hairline text-sm">
            {data.lost_by_month.map((m) => (
              <div key={m.month} className="flex justify-between py-1.5">
                <dt>{m.month}</dt>
                <dd className="font-semibold tabular-nums">{m.gyms}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title={t("admin.smsSold")}>
          <dl className="divide-y divide-hairline text-sm">
            {data.sms_sold_by_month.map((m) => (
              <div key={m.month} className="flex justify-between py-1.5">
                <dt>{m.month}</dt>
                <dd className="tabular-nums">
                  {m.credits} · <Money paisa={m.amount} />
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </div>
  );
}
