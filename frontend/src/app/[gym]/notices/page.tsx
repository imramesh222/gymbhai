"use client";

import { EmptyState } from "@/components/ui/Card";
import { t } from "@/i18n";
import { formatDateTime } from "@/lib/dates";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

export default function MemberNotices() {
  const { me } = useMember();
  const { data } = useLoad(() => memberApi.notices(), []);
  if (!me) return null;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{t("app.notices")}</h1>
      {data?.length === 0 && <EmptyState title={t("notices.none")} />}
      {data?.map((n) => (
        <article key={n.id} className="rounded-2xl bg-white p-4">
          <h2 className="font-semibold">{n.title}</h2>
          <p className="mt-1 text-sm whitespace-pre-line text-slate-700">{n.body}</p>
          <p className="mt-2 text-xs text-slate-500">
            {formatDateTime(n.published_at, me.gym.date_display)}
          </p>
        </article>
      ))}
    </div>
  );
}
