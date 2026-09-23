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
  const brand = me.gym.brand_color ?? "#1d5fd1";
  const color = state.days_left <= 3 || !active ? "#d97706" : brand;

  return (
    <div className="space-y-4">
      <p className="text-xl font-bold tracking-tight text-slate-900">
        {t("app.home.hello", { name: me.name.split(" ")[0] })}
      </p>

      <div className="flex items-center gap-4 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
        <svg viewBox="0 0 120 120" className="size-28 shrink-0 -rotate-90">
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke="#e9eef5"
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
          <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            {active
              ? t("app.home.daysLeft")
              : t(`app.home.status.${state.status}` as MessageKey)}
          </p>
          {state.plan_name && (
            <p className="mt-1 font-semibold text-slate-900">{state.plan_name}</p>
          )}
          {state.valid_until && (
            <p className="mt-0.5 text-sm text-slate-600">
              {state.status === "expired"
                ? t("app.home.expiredOn")
                : t("app.home.until")}{" "}
              {formatDate(state.valid_until, me.gym.date_display)}
            </p>
          )}
          {state.dues > 0 && (
            <p className="mt-1.5 inline-flex rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-200/70">
              {t("app.home.owes")} <Money paisa={state.dues} className="ml-1" />
            </p>
          )}
        </div>
      </div>

      {(!active || state.days_left <= 7) && (
        <Link
          href={`/${slug}/renew`}
          className="block rounded-2xl py-3.5 text-center font-semibold text-white shadow-raised transition active:translate-y-px"
          style={{ background: brand }}
        >
          {t("app.home.renew")}
        </Link>
      )}

      {/* The reason the app exists: one tap from opening it to the door. */}
      <div className="rounded-3xl bg-surface p-5 text-center shadow-raised ring-1 ring-hairline">
        <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
          {t("app.home.showAtDoor")}
        </p>
        <div className="mt-4 flex justify-center">
          <div className="rounded-2xl bg-white p-3 ring-1 ring-hairline">
            <LiveQr identity={me.qr} />
          </div>
        </div>
        <p className="mt-3 inline-flex rounded-full bg-slate-100 px-3 py-1 font-mono text-xs tracking-wider text-slate-600">
          {me.member_code}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
          <p className="text-3xl font-bold tracking-tight text-slate-900">
            {me.visits_this_month}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {t("app.home.visitsThisMonth")}
          </p>
        </div>
        <div className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
          <p className="text-3xl font-bold tracking-tight text-slate-900">
            {me.streak_weeks}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">{t("app.home.streak")}</p>
        </div>
      </div>

      {me.latest_notice && (
        <Link
          href={`/${slug}/notices`}
          className="block rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline transition active:translate-y-px"
        >
          <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            {t("app.home.notice")}
          </p>
          <p className="mt-1 font-semibold text-slate-900">{me.latest_notice.title}</p>
          <p className="line-clamp-2 text-sm text-slate-600">{me.latest_notice.body}</p>
        </Link>
      )}
    </div>
  );
}
