"use client";

import Link from "next/link";

import { LiveQr } from "@/components/memberApp/LiveQr";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { formatDate } from "@/lib/dates";
import { useMember } from "@/lib/memberSession";

const RING = 2 * Math.PI * 52;

/** Days left, the QR for the door, visits and the latest notice (§7). */
export default function MemberHome() {
  const { me, slug } = useMember();
  if (!me) return null;
  const { state } = me;
  const active = state.status === "active" || state.status === "frozen";
  // A full ring is a month; more just stays full.
  const filled = active ? Math.min(state.days_left / 30, 1) : 0;
  const color =
    state.days_left <= 3 || !active ? "#d97706" : (me.gym.brand_color ?? "#1d5fd1");

  return (
    <div className="space-y-5">
      <p className="text-lg font-semibold">
        {t("app.home.hello", { name: me.name.split(" ")[0] })}
      </p>

      <div className="flex items-center gap-4 rounded-2xl bg-white p-4 shadow-sm">
        <svg viewBox="0 0 120 120" className="size-28 shrink-0 -rotate-90">
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke="#e2e8f0"
            strokeWidth="12"
          />
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${filled * RING} ${RING}`}
          />
          <text
            x="60"
            y="60"
            textAnchor="middle"
            dominantBaseline="central"
            className="rotate-90 fill-slate-900 text-3xl font-bold"
            style={{ transformOrigin: "60px 60px" }}
          >
            {active ? state.days_left : 0}
          </text>
        </svg>
        <div className="min-w-0">
          <p className="text-sm text-slate-500">
            {active
              ? t("app.home.daysLeft")
              : t(`app.home.status.${state.status}` as MessageKey)}
          </p>
          {state.plan_name && <p className="font-medium">{state.plan_name}</p>}
          {state.valid_until && (
            <p className="text-sm text-slate-600">
              {state.status === "expired"
                ? t("app.home.expiredOn")
                : t("app.home.until")}{" "}
              {formatDate(state.valid_until, me.gym.date_display)}
            </p>
          )}
          {state.dues > 0 && (
            <p className="text-sm font-medium text-amber-700">
              {t("app.home.owes")} <Money paisa={state.dues} />
            </p>
          )}
        </div>
      </div>

      {(!active || state.days_left <= 7) && (
        <Link
          href={`/${slug}/renew`}
          className="block rounded-xl py-3 text-center font-semibold text-white"
          style={{ background: me.gym.brand_color ?? "#1d5fd1" }}
        >
          {t("app.home.renew")}
        </Link>
      )}

      <div className="rounded-2xl bg-white p-4 text-center shadow-sm">
        <p className="mb-3 text-sm font-medium text-slate-700">
          {t("app.home.showAtDoor")}
        </p>
        <LiveQr identity={me.qr} />
        <p className="mt-2 text-xs text-slate-500">{me.member_code}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-white p-4 shadow-sm">
          <p className="text-2xl font-bold">{me.visits_this_month}</p>
          <p className="text-xs text-slate-500">{t("app.home.visitsThisMonth")}</p>
        </div>
        <div className="rounded-2xl bg-white p-4 shadow-sm">
          <p className="text-2xl font-bold">{me.streak_weeks}</p>
          <p className="text-xs text-slate-500">{t("app.home.streak")}</p>
        </div>
      </div>

      {me.latest_notice && (
        <Link
          href={`/${slug}/notices`}
          className="block rounded-2xl bg-white p-4 shadow-sm"
        >
          <p className="text-xs font-semibold text-slate-500 uppercase">
            {t("app.home.notice")}
          </p>
          <p className="font-medium">{me.latest_notice.title}</p>
          <p className="line-clamp-2 text-sm text-slate-600">{me.latest_notice.body}</p>
        </Link>
      )}
    </div>
  );
}
