"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { DateInput, TextArea } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { addDays, daysBetween, formatDate, todayInNepal } from "@/lib/dates";
import { useLive } from "@/lib/live";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

/**
 * Going away? Ask the gym to pause the membership (PLAN.md §16.3, 8.6): the
 * dates and why; staff approve or reject, and the member hears either way.
 */
export default function FreezePage() {
  const { me, slug } = useMember();
  const latest = useLoad(() => memberApi.latestFreeze(), []);
  useLive(["freeze_request", "member"], latest.reload);
  const today = todayInNepal();
  const [from, setFrom] = useState(addDays(today, 1));
  const [to, setTo] = useState(addDays(today, 14));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  if (!me || latest.data === undefined) {
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  }
  const display = me.gym.date_display;
  const last = latest.data;
  const days = daysBetween(from, to) + 1;

  if (last?.status === "pending") {
    return (
      <div className="space-y-4 text-center">
        <h1 className="text-xl font-semibold">{t("app.freeze.waiting")}</h1>
        <p className="text-slate-600">
          {formatDate(last.from_date, display)} → {formatDate(last.to_date, display)}
        </p>
        <Button
          variant="secondary"
          onClick={async () => {
            await memberApi.withdrawFreeze(last.id);
            latest.reload();
          }}
        >
          {t("app.renew.withdraw")}
        </Button>
      </div>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        setError(null);
        try {
          await memberApi.askToFreeze({ from_date: from, to_date: to, reason });
          latest.reload();
        } catch (err) {
          setError(errorMessage(err));
        } finally {
          setPending(false);
        }
      }}
    >
      <h1 className="text-xl font-semibold">{t("app.freeze.title")}</h1>
      <p className="text-sm text-slate-600">{t("app.freeze.help")}</p>
      {last?.status === "approved" && (
        <Notice tone="success">
          {t("app.freeze.approved", {
            from: formatDate(last.from_date, display),
            to: formatDate(last.to_date, display),
          })}
        </Notice>
      )}
      {last?.status === "rejected" && (
        <Notice tone="warning">
          {t("app.freeze.rejected", { reason: last.reject_reason ?? "" })}
        </Notice>
      )}
      <div className="grid grid-cols-2 gap-3">
        <DateInput
          label={t("app.freeze.from")}
          value={from}
          onChange={setFrom}
          display={display}
          required
        />
        <DateInput
          label={t("app.freeze.to")}
          value={to}
          onChange={setTo}
          display={display}
          required
        />
      </div>
      {days > 0 && (
        <p className="text-sm text-slate-600">
          {t("app.freeze.days", { count: days })}
        </p>
      )}
      <TextArea
        label={t("app.freeze.reason")}
        value={reason}
        onChange={setReason}
        required
      />
      {error && <Notice tone="error">{error}</Notice>}
      <Button type="submit" block disabled={pending}>
        {t("app.freeze.send")}
      </Button>
      <Link href={`/${slug}`} className="block text-center text-sm text-slate-500">
        {t("common.back")}
      </Link>
    </form>
  );
}
