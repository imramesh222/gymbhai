"use client";

import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { t } from "@/i18n";
import { classesApi } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

import { dayOf, timeOf } from "./ClassDialog";

/** A member's classes on their profile (PLAN.md §19.4): what they booked,
 * whether they came, and their no-shows. */
export function MemberClassesTab({ memberId }: { memberId: string }) {
  const { date } = useGymCalendar();
  const { data, error } = useLoad(() => classesApi.ofMember(memberId), [memberId]);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <ListSkeleton rows={2} />;
  return (
    <Card>
      {data.no_shows > 0 && (
        <p className="mb-2 text-sm font-medium text-amber-800">
          {t("member.noShows", { count: data.no_shows })}
        </p>
      )}
      {data.bookings.length === 0 ? (
        <EmptyState title={t("member.noClasses")} />
      ) : (
        <ul className="divide-y divide-hairline">
          {data.bookings.map((b) => (
            <li
              key={b.id}
              className="flex items-center justify-between gap-3 py-2 text-sm"
            >
              <span>
                <span className="font-medium">{b.type_name}</span>
                <span className="text-slate-500">
                  {" "}
                  · {date(dayOf(b.starts_at))} {timeOf(b.starts_at)}
                </span>
              </span>
              <span className="shrink-0 text-xs text-slate-600">
                {b.cancelled
                  ? t("classes.cancelled")
                  : b.status === "cancelled"
                    ? `${t("classes.bookingCancelled")}${b.late ? ` · ${t("classes.late")}` : ""}`
                    : b.status === "waitlist"
                      ? t("classes.waitlist")
                      : b.came === true
                        ? t("classes.came")
                        : b.came === false
                          ? t("classes.noShow")
                          : t("app.classes.booked")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
