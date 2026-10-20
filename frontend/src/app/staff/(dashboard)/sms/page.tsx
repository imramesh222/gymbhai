"use client";

import { MessageItem } from "@/components/messages/MessageItem";
import { Notice } from "@/components/Notice";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { messagesApi } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

export default function SmsPage() {
  const { display } = useGymCalendar();
  const { data, error, reload } = useLoad(() => messagesApi.smsLog(), []);
  // Sent, failed, delivered or read (§19.3).
  useLive(["message"], reload);
  return (
    <div className="space-y-4">
      <PageHeader title={t("sms.title")} />
      {error && <Notice tone="error">{error}</Notice>}
      {data && (
        <>
          <Card>
            <p className="text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
              {t("sms.balance")}
            </p>
            <p className="mt-1.5 text-3xl font-bold tracking-tight text-slate-900">
              {data.balance}
            </p>
            {data.balance <= 10 && (
              <p className="mt-1 text-sm text-amber-800">{t("sms.low")}</p>
            )}
          </Card>
          <Card title={t("sms.log")}>
            {data.items.length === 0 && <EmptyState title={t("sms.none")} />}
            <ul className="divide-y divide-hairline">
              {data.items.map((m) => (
                <MessageItem key={m.id} message={m} display={display} showTo />
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
