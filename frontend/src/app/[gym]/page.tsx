"use client";

import Link from "next/link";

import { LiveQr } from "@/components/memberApp/LiveQr";
import { InstallPrompt } from "@/components/memberApp/InstallPrompt";
import { OwnAppPrompt } from "@/components/memberApp/OwnAppPrompt";
import { PushPrompt } from "@/components/memberApp/PushPrompt";
import { Money } from "@/components/ui/Money";
import { plural, t, type MessageKey } from "@/i18n";
import { describeHours } from "@/lib/accessHours";
import { formatDate, type DateDisplay } from "@/lib/dates";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";
import type { MemberTraining } from "@shared/types";

const RING = 2 * Math.PI * 52;

/** Days left, the QR for the door, visits and the latest notice (§7). */
export default function MemberHome() {
  const { me, slug } = useMember();
  // Whether the gym has its own app in the stores (§20.3).
  const gym = useLoad(() => memberApi.gym(slug), [slug]);
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
          {/* A family or couple plan (§19.1). */}
          {state.plan_with && state.plan_with.length > 0 && (
            <p className="text-sm text-slate-600">
              {t("app.home.with", { names: state.plan_with.join(", ") })}
            </p>
          )}
          {state.paid_by && (
            <p className="text-sm text-slate-600">
              {t("app.home.paidBy", { name: state.paid_by })}
            </p>
          )}
          {state.valid_until && (
            <p className="mt-0.5 text-sm text-slate-600">
              {state.status === "expired"
                ? t("app.home.expiredOn")
                : t("app.home.until")}{" "}
              {formatDate(state.valid_until, me.gym.date_display)}
            </p>
          )}
          {state.visit_limit !== null && state.visits_left !== null && (
            <p className="mt-0.5 text-sm font-medium text-slate-700">
              {t("app.home.visitsLeft", {
                left: state.visits_left,
                limit: state.visit_limit,
              })}
            </p>
          )}
          {state.access_hours && (
            <p className="mt-0.5 text-xs text-slate-500">
              {t("app.home.hours", { hours: describeHours(state.access_hours) ?? "" })}
            </p>
          )}
          {state.dues > 0 && (
            <p className="mt-1.5 inline-flex rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-200/70">
              {t("app.home.owes")} <Money paisa={state.dues} className="ml-1" />
            </p>
          )}
          {!!state.group_dues && state.group_dues > 0 && (
            <p className="mt-1.5 inline-flex rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-200/70">
              {t("app.home.groupOwes")}{" "}
              <Money paisa={state.group_dues} className="ml-1" />
            </p>
          )}
        </div>
      </div>

      {state.status === "active" && (
        <Link
          href={`/${slug}/freeze`}
          className="block text-center text-sm font-medium text-slate-600 underline-offset-2 hover:underline"
        >
          {t("app.freeze.link")}
        </Link>
      )}

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

      {me.has_classes && (
        <Link
          href={`/${slug}/classes`}
          className="flex items-center justify-between gap-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">
              {t("app.home.classes")}
            </p>
            <p className="text-xs text-slate-500">{t("app.home.classesHelp")}</p>
          </div>
          <span aria-hidden className="text-lg text-slate-400">
            ›
          </span>
        </Link>
      )}

      <Link
        href={`/${slug}/progress`}
        className="flex items-center justify-between gap-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
      >
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">
            {t("app.home.progress")}
          </p>
          <p className="text-xs text-slate-500">{t("app.home.progressHelp")}</p>
        </div>
        <span aria-hidden className="text-lg text-slate-400">
          ›
        </span>
      </Link>

      {me.busy && (
        <div className="flex items-center gap-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
          <span
            aria-hidden
            className={`size-3 shrink-0 rounded-full ${
              me.busy === "quiet"
                ? "bg-emerald-500"
                : me.busy === "normal"
                  ? "bg-amber-400"
                  : "bg-red-500"
            }`}
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">
              {t("app.busy.label")}: {t(`app.busy.${me.busy}` as MessageKey)}
            </p>
            <p className="text-xs text-slate-500">
              {t(`app.busy.hint.${me.busy}` as MessageKey)}
            </p>
          </div>
        </div>
      )}

      {(me.training ?? []).map((pt) => (
        <Training key={pt.id} pt={pt} display={me.gym.date_display} />
      ))}

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

      {gym.data?.app ? (
        <OwnAppPrompt app={gym.data.app} color={brand} />
      ) : (
        <InstallPrompt slug={slug} color={brand} />
      )}
      <PushPrompt slug={slug} color={brand} />

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

/** Their personal training: plan, trainer, sessions or days left (§18.3). */
function Training({ pt, display }: { pt: MemberTraining; display: DateDisplay }) {
  const until = formatDate(pt.end_date, display);
  return (
    <div className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
      <p className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
        {t("app.home.training")}
      </p>
      <p className="mt-1 font-semibold text-slate-900">{pt.plan_name}</p>
      {pt.trainer_name && (
        <p className="text-sm text-slate-600">
          {t("app.home.trainer", { name: pt.trainer_name })}
        </p>
      )}
      <p className="mt-0.5 text-sm font-medium text-slate-700">
        {pt.status === "upcoming"
          ? t("app.home.trainingStarts", { date: formatDate(pt.start_date, display) })
          : pt.sessions !== null
            ? t("app.home.sessionsLeft", {
                left: pt.sessions_left ?? 0,
                total: pt.sessions,
              })
            : plural(
                pt.days_left,
                "app.home.trainingDays.one",
                "app.home.trainingDays.other",
                {
                  date: until,
                },
              )}
      </p>
      {pt.status === "active" && pt.sessions !== null && (
        <p className="text-xs text-slate-500">
          {t("app.home.until")} {until}
        </p>
      )}
      {pt.dues > 0 && (
        <p className="mt-1.5 inline-flex rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-200/70">
          {t("app.home.owes")} <Money paisa={pt.dues} className="ml-1" />
        </p>
      )}
    </div>
  );
}
