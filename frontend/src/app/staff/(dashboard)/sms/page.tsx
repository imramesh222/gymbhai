"use client";

import Link from "next/link";

import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { t, type MessageKey } from "@/i18n";
import { messagesApi } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

const STATUS_STYLE: Record<string, string> = {
  sent: "text-emerald-700",
  queued: "text-slate-500",
  failed: "text-red-700",
  no_credit: "text-amber-700",
};

export default function SmsPage() {
  const { display } = useGymCalendar();
  const { data, error } = useLoad(() => messagesApi.smsLog(), []);
  return (
    <div className="space-y-4">
      <PageHeader title={t("sms.title")} />
      {error && <Notice tone="error">{error}</Notice>}
      {data && (
        <>
          <Card>
            <p className="text-sm text-slate-600">{t("sms.balance")}</p>
            <p className="text-3xl font-bold text-brand-900">{data.balance}</p>
            {data.balance <= 10 && (
              <p className="mt-1 text-sm text-amber-800">{t("sms.low")}</p>
            )}
          </Card>
          <Card title={t("sms.log")}>
            {data.items.length === 0 && (
              <p className="text-sm text-slate-500">{t("sms.none")}</p>
            )}
            <ul className="divide-y divide-slate-100">
              {data.items.map((m) => (
                <li key={m.id} className="py-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="font-medium">
                      {m.member_id ? (
                        <Link
                          href={`/staff/members/${m.member_id}`}
                          className="hover:underline"
                        >
                          {m.to}
                        </Link>
                      ) : (
                        m.to
                      )}{" "}
                      <span className="font-normal text-slate-500">
                        · {t(`sms.kind.${m.kind}` as MessageKey)}
                      </span>
                    </span>
                    <span className={STATUS_STYLE[m.status]}>
                      {t(`sms.status.${m.status}` as MessageKey)}
                    </span>
                  </div>
                  <p className="text-slate-700">{m.body}</p>
                  <p className="text-xs text-slate-500">
                    {formatDateTime(m.created_at, display)} ·{" "}
                    {t("sms.parts", { count: m.segments, characters: m.body.length })}
                    {m.error && ` · ${m.error}`}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
