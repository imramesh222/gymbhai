"use client";

import { Notice } from "@/components/Notice";
import { plural, t, type MessageKey } from "@/i18n";
import { useAuth } from "@/lib/auth";
import { memberAppUrl } from "@/lib/slug";

const CALENDAR: Record<string, MessageKey> = {
  ad: "calendar.ad",
  bs: "calendar.bs",
  both: "calendar.both",
};

export default function TodayPage() {
  const { me } = useAuth();
  if (!me) return null;

  if (!me.gym) {
    return <Notice>{t("staff.platformAdmin")}</Notice>;
  }

  const { gym, subscription } = me;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-brand-900">
        {t("staff.welcome", { name: me.staff.name })}
      </h1>
      {subscription?.status === "trial" && (
        <Notice tone={subscription.days_left <= 3 ? "warning" : "info"}>
          {subscription.days_left > 0
            ? plural(
                subscription.days_left,
                "staff.trialDaysLeft.one",
                "staff.trialDaysLeft.other",
              )
            : t("staff.trialEnded")}
        </Notice>
      )}
      <p className="text-slate-700">
        {t("staff.memberAppAt", { url: memberAppUrl(gym.slug) })}
      </p>
      <p className="text-sm text-slate-500">
        {t("staff.calendar", {
          months: t(CALENDAR[gym.settings.plan_months]),
          display: t(CALENDAR[gym.settings.date_display]),
        })}
      </p>
    </div>
  );
}
