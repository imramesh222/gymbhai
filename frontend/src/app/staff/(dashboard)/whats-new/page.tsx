"use client";

import { useEffect, useRef } from "react";

import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { t } from "@/i18n";
import { changelogApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** What's new in GymBhai (PLAN.md §16.5, 10.4). Opening it clears the dot. */
export default function WhatsNewPage() {
  const { refreshMe } = useAuth();
  const { display } = useGymCalendar();
  const { data } = useLoad(() => changelogApi.list(), []);
  // Once per visit: refreshing who's signed in hands back a new refreshMe.
  const marked = useRef(false);
  useEffect(() => {
    if (marked.current) return;
    marked.current = true;
    changelogApi
      .seen()
      .then(() => refreshMe())
      .catch(() => undefined);
  }, [refreshMe]);
  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.whatsNew")} subtitle={t("whatsNew.subtitle")} />
      {!data && <PageSkeleton label={t("common.loading")} />}
      {data?.length === 0 && <EmptyState title={t("whatsNew.none")} />}
      {data?.map((entry) => (
        <Card
          key={entry.id}
          title={entry.title}
          actions={
            <span className="text-xs text-slate-500">
              {formatDate(entry.published_at!.slice(0, 10), display)}
            </span>
          }
        >
          <p className="text-sm whitespace-pre-line text-slate-700">{entry.body}</p>
        </Card>
      ))}
    </div>
  );
}
