"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, MoneyInput, TextArea } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { ApiError, errorMessage, paymentRequestsApi } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import type { PaymentRequest } from "@/lib/memberApi";
import { useLoad } from "@/lib/useLoad";

/**
 * Members' app payments waiting for approval (§5.4). Check the gym's eSewa or
 * bank app for the money, then approve or reject with a reason.
 */
export default function PaymentRequestsPage() {
  const { display } = useGymCalendar();
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const { data, reload } = useLoad(() => paymentRequestsApi.list(status), [status]);
  const [open, setOpen] = useState<{
    request: PaymentRequest;
    action: "approve" | "reject";
  } | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader title={t("requests.title")} subtitle={t("requests.help")} />
      <div className="flex gap-2">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={`rounded-full border px-3 py-1 text-sm ${status === s ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300"}`}
          >
            {t(`app.request.${s}` as MessageKey)}
          </button>
        ))}
      </div>
      {data?.length === 0 && (
        <p className="text-sm text-slate-500">{t("requests.none")}</p>
      )}
      {data?.map((r) => (
        <Card key={r.id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="text-sm">
              <Link
                href={`/staff/members/${r.member_id}`}
                className="font-semibold hover:underline"
              >
                {r.member_name} · {r.member_code}
              </Link>
              <p>
                {r.plan_name} · <Money paisa={r.amount} className="font-semibold" />
                {r.expected_total !== null && r.expected_total !== r.amount && (
                  <span className="text-amber-700">
                    {" "}
                    ({t("requests.expected")} <Money paisa={r.expected_total} />)
                  </span>
                )}
              </p>
              <p className="text-slate-600">
                {r.method_label ?? "—"} · {t("payment.transactionRef")}:{" "}
                {r.transaction_ref ?? "—"}
              </p>
              <p className="text-xs text-slate-500">
                {formatDateTime(r.created_at, display)}
              </p>
              {r.reject_reason && <p className="text-red-700">{r.reject_reason}</p>}
              {r.reviewed_by_name && (
                <p className="text-xs text-slate-500">
                  {t("requests.by", { name: r.reviewed_by_name })}
                </p>
              )}
            </div>
            {r.screenshot_url && (
              <a href={r.screenshot_url} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={r.screenshot_url}
                  alt={t("app.renew.screenshot")}
                  className="h-32 rounded border"
                />
              </a>
            )}
          </div>
          {r.status === "pending" && (
            <div className="mt-3 flex gap-2">
              <Button onClick={() => setOpen({ request: r, action: "approve" })}>
                {t("requests.approve")}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setOpen({ request: r, action: "reject" })}
              >
                {t("requests.reject")}
              </Button>
            </div>
          )}
        </Card>
      ))}
      {open && (
        <Decide
          request={open.request}
          action={open.action}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function Decide({
  request,
  action,
  onClose,
  onDone,
}: {
  request: PaymentRequest;
  action: "approve" | "reject";
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [price, setPrice] = useState<number | null>(null);
  const [part, setPart] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mismatch =
    request.expected_total !== null && request.expected_total !== request.amount;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      if (action === "reject") await paymentRequestsApi.reject(request.id, reason);
      else
        await paymentRequestsApi.approve(request.id, {
          price,
          accept_part_payment: part,
        });
      onDone();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "amount_mismatch"
          ? t("requests.mismatch")
          : errorMessage(err),
      );
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={action === "approve" ? t("requests.approve") : t("requests.reject")}
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        {action === "reject" ? (
          <TextArea
            label={t("requests.reason")}
            value={reason}
            onChange={setReason}
            required
          />
        ) : (
          <>
            <p className="text-sm">{t("requests.checkMoney")}</p>
            {mismatch && (
              <>
                <Notice tone="warning">{t("requests.mismatch")}</Notice>
                <MoneyInput
                  label={t("requests.adjustPrice")}
                  value={price}
                  onChange={setPrice}
                />
                <Checkbox
                  label={t("requests.acceptPart")}
                  checked={part}
                  onChange={setPart}
                />
              </>
            )}
          </>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button
          type="submit"
          block
          variant={action === "reject" ? "danger" : "primary"}
        >
          {action === "approve" ? t("requests.approve") : t("requests.reject")}
        </Button>
      </form>
    </Dialog>
  );
}
