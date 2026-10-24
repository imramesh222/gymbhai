"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { adminApi, errorMessage, type GymReferral } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

const STATUSES: GymReferral["status"][] = ["ready", "pending", "rewarded", "rejected"];

/**
 * Gyms that sent us gyms (PLAN.md §16.5, 10.5). Ready: the referred gym has
 * paid; reward gives both a free month.
 */
export default function AdminReferralsPage() {
  const toast = useToast();
  const [status, setStatus] = useState<GymReferral["status"]>("ready");
  const { data, reload } = useLoad(() => adminApi.referrals(status), [status]);

  async function act(action: () => Promise<void>, done: MessageKey) {
    try {
      await action();
      toast.success(t(done));
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("referrals.title")} subtitle={t("referrals.adminHelp")} />
      <div className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
            className={`rounded-full border px-3 py-1 text-sm ${status === s ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300"}`}
          >
            {t(`referrals.status.${s}` as MessageKey)}
          </button>
        ))}
      </div>
      {data?.length === 0 && <EmptyState title={t("referrals.none")} />}
      {data?.map((r) => (
        <Card key={r.id}>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div>
              <p className="font-semibold">
                {t("referrals.sent", { from: r.referrer_name, to: r.referred_name })}
              </p>
              <p className="text-xs text-slate-500">
                {formatDateTime(r.created_at, "ad")}
                {r.note && ` · ${r.note}`}
              </p>
            </div>
            {r.status === "ready" && (
              <div className="flex gap-2">
                <Button
                  onClick={() =>
                    act(() => adminApi.rewardReferral(r.id), "referrals.rewarded")
                  }
                >
                  {t("referrals.reward")}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    const reason = window.prompt(t("requests.reason"));
                    if (reason)
                      void act(
                        () => adminApi.rejectReferral(r.id, reason),
                        "referrals.rejected",
                      );
                  }}
                >
                  {t("requests.reject")}
                </Button>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
