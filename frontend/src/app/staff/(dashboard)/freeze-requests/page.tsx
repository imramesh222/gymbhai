"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { TextArea } from "@/components/ui/inputs";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, freezeRequestsApi, type FreezeRequest } from "@/lib/api";
import { addDays, daysBetween, formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

type Status = "pending" | "approved" | "rejected";

function RejectDialog({
  request,
  onClose,
  onDone,
}: {
  request: FreezeRequest;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open onClose={onClose} title={t("freezes.reject")}>
      <Form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await freezeRequestsApi.reject(request.id, reason);
            onDone();
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
      >
        <TextArea
          label={t("freezes.rejectReason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block>
          {t("freezes.reject")}
        </Button>
      </Form>
    </Dialog>
  );
}

/**
 * Freezes members asked for in the app (PLAN.md §16.3, 8.6). Approving makes
 * the freeze, as at the desk; rejecting tells the member why.
 */
export default function FreezeRequestsPage() {
  const { date, display } = useGymCalendar();
  const toast = useToast();
  const confirm = useConfirm();
  const [status, setStatus] = useState<Status>("pending");
  const { data, error, reload } = useLoad(
    () => freezeRequestsApi.list(status),
    [status],
  );
  // A new one from the app, or another staff member got there first.
  useLive(["freeze_request"], reload);
  const [rejecting, setRejecting] = useState<FreezeRequest | null>(null);

  async function approve(r: FreezeRequest) {
    const days = daysBetween(r.from_date, r.to_date) + 1;
    const ok = await confirm({
      title: t("freezes.approve"),
      message: t("freezes.approveConfirm", {
        name: r.member_name ?? "",
        days,
        end: r.ends_on ? date(addDays(r.ends_on, days)) : "—",
      }),
      confirmLabel: t("freezes.approve"),
    });
    if (!ok) return;
    try {
      await freezeRequestsApi.approve(r.id);
      toast.success(t("freezes.approved", { name: r.member_name ?? "" }));
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
      reload();
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("freezes.title")} subtitle={t("freezes.help")} />
      <div className="flex gap-2">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
            className={`rounded-full border px-3 py-1 text-sm ${status === s ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300"}`}
          >
            {t(`app.request.${s}` as MessageKey)}
          </button>
        ))}
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <PageSkeleton label={t("common.loading")} />}
      {data?.length === 0 && <EmptyState title={t("freezes.none")} />}
      {data?.map((r) => (
        <Card key={r.id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-0.5 text-sm">
              <Link
                href={`/staff/members/${r.member_id}`}
                className="font-semibold hover:underline"
              >
                {r.member_name} · {r.member_code}
              </Link>
              <p>
                {date(r.from_date)} → {date(r.to_date)} (
                {t("freezes.days", { count: daysBetween(r.from_date, r.to_date) + 1 })})
              </p>
              <p className="text-slate-600">“{r.reason}”</p>
              <p className="text-xs text-slate-500">
                {r.plan_name}
                {r.ends_on && ` · ${t("freezes.endsOn", { date: date(r.ends_on) })}`}
                {" · "}
                {formatDateTime(r.created_at, display)}
              </p>
              {r.reject_reason && <p className="text-red-700">{r.reject_reason}</p>}
              {r.reviewed_by_name && (
                <p className="text-xs text-slate-500">
                  {t("freezes.by", { name: r.reviewed_by_name })}
                </p>
              )}
            </div>
            {r.status === "pending" && (
              <div className="flex gap-2">
                <Button onClick={() => approve(r)}>{t("freezes.approve")}</Button>
                <Button variant="secondary" onClick={() => setRejecting(r)}>
                  {t("freezes.reject")}
                </Button>
              </div>
            )}
          </div>
        </Card>
      ))}
      {rejecting && (
        <RejectDialog
          request={rejecting}
          onClose={() => setRejecting(null)}
          onDone={() => {
            toast.success(t("freezes.rejected"));
            setRejecting(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
