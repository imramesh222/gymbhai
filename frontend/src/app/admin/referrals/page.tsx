"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { FilterChips } from "@/components/ui/FilterChips";
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
  const [rejecting, setRejecting] = useState<GymReferral | null>(null);

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
      <FilterChips
        label={t("members.filters")}
        chips={STATUSES.map((s) => ({
          key: s,
          label: t(`referrals.status.${s}` as MessageKey),
        }))}
        value={status}
        onChange={setStatus}
      />
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
                <Button variant="secondary" onClick={() => setRejecting(r)}>
                  {t("requests.reject")}
                </Button>
              </div>
            )}
          </div>
        </Card>
      ))}
      {rejecting && (
        <RejectDialog
          referral={rejecting}
          onClose={() => setRejecting(null)}
          onReject={async (reason) => {
            await act(
              () => adminApi.rejectReferral(rejecting.id, reason),
              "referrals.rejected",
            );
            setRejecting(null);
          }}
        />
      )}
    </div>
  );
}

/** Why a referral gets no free month: a note for us, never shown to a gym. */
function RejectDialog({
  referral,
  onClose,
  onReject,
}: {
  referral: GymReferral;
  onClose: () => void;
  onReject: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open onClose={onClose} title={t("referrals.rejectTitle")}>
      <Form onSubmit={() => onReject(reason.trim())} className="space-y-3">
        <p className="text-sm text-slate-600">
          {t("referrals.sent", {
            from: referral.referrer_name,
            to: referral.referred_name,
          })}
        </p>
        <Field
          label={t("referrals.rejectReason")}
          help={t("referrals.rejectReasonHelp", { status: t("refer.status.rejected") })}
          value={reason}
          onChange={setReason}
          required
        />
        <Button type="submit" block variant="danger" disabled={!reason.trim()}>
          {t("requests.reject")}
        </Button>
      </Form>
    </Dialog>
  );
}
