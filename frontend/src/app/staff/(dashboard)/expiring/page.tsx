"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, messagesApi, type Member } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Who to chase: ending this week, ending today, lapsed this month (§7). */
export default function ExpiringPage() {
  const { can } = useAuth();
  const { date } = useGymCalendar();
  const { data, error } = useLoad(() => messagesApi.expiring(), []);
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const [sendError, setSendError] = useState<string | null>(null);

  async function remind(member: Member) {
    setSendError(null);
    try {
      await messagesApi.smsMember(member.id, { reminder: true });
      setSent({ ...sent, [member.id]: true });
    } catch (err) {
      setSendError(errorMessage(err));
    }
  }

  const sections: [MessageKey, Member[] | undefined][] = [
    ["expiring.today", data?.due_today],
    ["expiring.week", data?.due_this_week],
    ["expiring.lapsed", data?.lapsed],
  ];

  return (
    <div className="space-y-4">
      <PageHeader title={t("expiring.title")} subtitle={t("expiring.subtitle")} />
      {(error || sendError) && <Notice tone="error">{error || sendError}</Notice>}
      {!data && !error && (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      )}
      {sections.map(([title, members]) =>
        members ? (
          <Card key={title} title={`${t(title)} (${members.length})`}>
            {members.length === 0 && (
              <p className="text-sm text-slate-500">{t("expiring.none")}</p>
            )}
            <ul className="divide-y divide-hairline">
              {members.map((m) => (
                <li
                  key={m.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <Link
                    href={`/staff/members/${m.id}`}
                    className="min-w-0 hover:underline"
                  >
                    <p className="truncate font-medium">{m.name}</p>
                    <p className="text-xs text-slate-500">
                      {m.current?.plan_name} · {date(m.valid_until)}
                      {m.dues > 0 && (
                        <>
                          {" · "}
                          <span className="text-amber-700">
                            {t("members.owes")} <Money paisa={m.dues} />
                          </span>
                        </>
                      )}
                    </p>
                  </Link>
                  <div className="flex shrink-0 gap-2">
                    <a
                      href={`tel:${m.phone}`}
                      className="rounded-xl bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-card ring-1 ring-hairline transition hover:bg-slate-50"
                    >
                      {t("expiring.call")}
                    </a>
                    {can("messages.sms") && (
                      <Button
                        variant="secondary"
                        disabled={sent[m.id]}
                        onClick={() => void remind(m)}
                      >
                        {sent[m.id] ? t("expiring.sent") : t("expiring.remind")}
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        ) : null,
      )}
    </div>
  );
}
