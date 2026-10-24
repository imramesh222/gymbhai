"use client";

import {
  BellRing,
  CalendarCheck,
  CircleCheck,
  Receipt,
  RefreshCw,
  Snowflake,
  Wallet,
} from "lucide-react";

import { QrCode } from "@/components/QrCode";
import { localDigits, t } from "@/i18n";
import { formatRs } from "@/lib/money";

/**
 * Pictures of the product for the home page, drawn from the same pieces as
 * the real screens. Decorative: the words beside them say what matters, so
 * screen readers skip them (aria-hidden where they're used).
 */

const RING = 2 * Math.PI * 52;

function DaysRing({ days, filled }: { days: number; filled: number }) {
  return (
    <svg viewBox="0 0 120 120" className="size-16 shrink-0 -rotate-90">
      <circle cx="60" cy="60" r="52" fill="none" stroke="#e9eef5" strokeWidth="12" />
      <circle
        cx="60"
        cy="60"
        r="52"
        fill="none"
        stroke="var(--color-brand-600)"
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${filled * RING} ${RING}`}
      />
      <text
        x="60"
        y="60"
        textAnchor="middle"
        dominantBaseline="central"
        className="rotate-90 fill-slate-900 text-[34px] font-bold"
        style={{ transformOrigin: "60px 60px" }}
      >
        {localDigits(String(days))}
      </text>
    </svg>
  );
}

/** The member's app on a phone: days left and the QR for the door. */
export function PhoneMock() {
  return (
    <div className="relative mx-auto w-[16.5rem] rounded-[2.6rem] bg-slate-900 p-2.5 shadow-[0_50px_100px_-30px_rgba(0,0,0,0.85)] ring-1 ring-white/15 sm:w-[17.5rem]">
      <div className="overflow-hidden rounded-[2.1rem] bg-canvas">
        <div className="relative bg-linear-to-br from-brand-500 to-brand-700 px-4 pt-8 pb-5 text-white">
          <span className="absolute top-2.5 left-1/2 h-1.5 w-16 -translate-x-1/2 rounded-full bg-slate-900/40" />
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-xl bg-white/20 text-sm font-bold">
              {t("home.mock.gym").slice(0, 1)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{t("home.mock.gym")}</p>
              <p className="truncate text-xs text-white/75">{t("home.mock.member")}</p>
            </div>
          </div>
        </div>
        <div className="space-y-3 p-3.5">
          <p className="text-base font-bold text-slate-900">
            {t("app.home.hello", { name: t("home.mock.firstName") })}
          </p>
          <div className="flex items-center gap-3 rounded-2xl bg-white p-3 ring-1 ring-hairline">
            <DaysRing days={52} filled={0.58} />
            <div className="min-w-0">
              <p className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
                {t("app.home.daysLeft")}
              </p>
              <p className="text-sm font-semibold text-slate-900">
                {t("home.mock.plan")}
              </p>
            </div>
          </div>
          <div className="rounded-2xl bg-white p-3 text-center ring-1 ring-hairline">
            <p className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">
              {t("app.home.showAtDoor")}
            </p>
            <div className="mx-auto mt-2 w-fit">
              <QrCode
                value="https://app.gymbhai.com"
                size={128}
                label={t("app.home.showAtDoor")}
              />
            </div>
            <p className="mt-2 inline-block rounded-full bg-canvas px-2.5 py-0.5 text-[11px] tracking-[0.2em] text-slate-500">
              HFC-0179
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A notification-like card that floats beside the phone. */
function Floating({
  icon,
  tone,
  title,
  body,
  className,
}: {
  icon: React.ReactNode;
  tone: string;
  title: string;
  body: string;
  className: string;
}) {
  return (
    <div
      className={`absolute max-w-[15rem] items-center gap-3 rounded-2xl bg-white/95 p-3 pr-4 text-slate-900 shadow-[0_24px_48px_-20px_rgba(0,0,0,0.65)] ring-1 ring-black/5 backdrop-blur ${className}`}
    >
      <span
        className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${tone}`}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-pretty text-slate-500">{body}</p>
      </div>
    </div>
  );
}

/**
 * The phone, with what happens around it: a check-in, a payment, reminders.
 * The cards sit on the phone's frame and its empty corners, never over what
 * the screen says; on a phone, two of them, above and below it.
 */
export function HeroVisual() {
  return (
    <div className="relative mx-auto w-fit py-10" aria-hidden>
      <div className="absolute inset-6 -z-10 rounded-full bg-brand-500/30 blur-3xl" />
      <div className="relative">
        <PhoneMock />
        <Floating
          className="-top-7 -left-4 flex sm:-left-28"
          tone="bg-emerald-50 text-emerald-600"
          icon={<CircleCheck className="size-5" />}
          title={t("home.mock.checkedIn")}
          body={t("home.mock.checkedInAt")}
        />
        <Floating
          className="top-[8.6rem] -right-24 hidden sm:flex"
          tone="bg-brand-50 text-brand-700"
          icon={<Wallet className="size-5" />}
          title={t("home.mock.paid")}
          body={t("home.mock.paidBy", { amount: formatRs(1500_00) })}
        />
        <Floating
          className="-bottom-11 -left-4 flex sm:-left-28"
          tone="bg-amber-50 text-amber-600"
          icon={<BellRing className="size-5" />}
          title={t("home.mock.reminders")}
          body={t("home.mock.remindersTo", { count: 12 })}
        />
      </div>
    </div>
  );
}

/** What the door says: let in, or not. */
export function ScanChips() {
  return (
    <div className="space-y-2" aria-hidden>
      <p className="flex w-fit items-center gap-2 rounded-full bg-emerald-500/90 px-3.5 py-1.5 text-sm font-semibold text-white shadow-lg backdrop-blur">
        <span className="size-2 rounded-full bg-white" />
        {t("home.mock.scanOk", { count: 52 })}
      </p>
      <p className="flex w-fit items-center gap-2 rounded-full bg-amber-500/90 px-3.5 py-1.5 text-sm font-semibold text-white shadow-lg backdrop-blur">
        <span className="size-2 rounded-full bg-white" />
        {t("home.mock.scanExpired")}
      </p>
    </div>
  );
}

/** The members list: who's fine, who's ending, who owes. */
export function MembersMock() {
  const rows = [
    {
      name: t("home.mock.person1"),
      badge: t("status.active"),
      tone: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    },
    {
      name: t("home.mock.person2"),
      badge: t("home.mock.endsIn", { count: 3 }),
      tone: "bg-amber-50 text-amber-700 ring-amber-600/20",
    },
    {
      name: t("home.mock.person3"),
      badge: t("home.mock.owes", { amount: formatRs(500_00) }),
      tone: "bg-red-50 text-red-700 ring-red-600/20",
    },
  ];
  return (
    <ul
      className="divide-y divide-hairline rounded-2xl bg-white shadow-raised ring-1 ring-hairline"
      aria-hidden
    >
      {rows.map((row) => (
        <li
          key={row.name}
          className="flex items-center justify-between gap-3 px-4 py-2.5"
        >
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700">
              {row.name.slice(0, 1)}
            </span>
            <span className="truncate text-sm font-medium text-slate-900">
              {row.name}
            </span>
          </span>
          <span
            className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${row.tone}`}
          >
            {row.badge}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A reminder as it lands on the member's phone. */
export function SmsMock() {
  return (
    <div className="rounded-2xl bg-slate-50 p-3 ring-1 ring-hairline" aria-hidden>
      <p className="max-w-[18rem] rounded-2xl rounded-bl-md bg-white px-3.5 py-2.5 text-sm text-pretty text-slate-700 shadow-card ring-1 ring-hairline">
        {t("home.mock.sms")}
      </p>
    </div>
  );
}

/** A year of income as bars: the shape of a report, not real numbers. */
export function ChartMock() {
  const bars = [38, 52, 46, 61, 58, 72, 66, 79, 74, 88, 83, 96];
  return (
    <div className="rounded-2xl bg-white p-4 ring-1 ring-hairline" aria-hidden>
      <p className="text-xs font-medium text-slate-500">{t("home.mock.thisMonth")}</p>
      <p className="mt-0.5 text-2xl font-bold tracking-tight text-slate-900">
        {formatRs(4_86_500_00)}
      </p>
      <div className="mt-4 flex h-24 items-end gap-1.5">
        {bars.map((height, i) => (
          <span
            key={i}
            style={{ height: `${height}%` }}
            className={`flex-1 rounded-t-md ${
              i === bars.length - 1 ? "bg-brand-600" : "bg-brand-100"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

/** Ticks for what a staff member may do. */
export function StaffMock() {
  const ticks = [
    { key: "perm.memberships.sell", on: true },
    { key: "perm.payments.collect", on: true },
    { key: "perm.door.check_in", on: false },
  ] as const;
  return (
    <ul className="space-y-2" aria-hidden>
      {ticks.map((tick) => (
        <li
          key={tick.key}
          className="flex items-center gap-3 rounded-xl bg-white px-3.5 py-2.5 text-sm text-slate-700 ring-1 ring-hairline"
        >
          <span
            className={`flex size-5 items-center justify-center rounded-md text-[11px] font-bold ${
              tick.on ? "bg-brand-600 text-white" : "ring-1 ring-slate-300"
            }`}
          >
            {tick.on ? "✓" : ""}
          </span>
          {t(tick.key)}
        </li>
      ))}
    </ul>
  );
}

/** What a member does from the app, without coming to the desk. */
export function AppMock() {
  const actions = [
    { key: "app.home.renew", icon: RefreshCw },
    { key: "app.freeze.title", icon: Snowflake },
    { key: "app.home.classes", icon: CalendarCheck },
    { key: "app.tab.payments", icon: Receipt },
  ] as const;
  return (
    <ul className="grid grid-cols-2 gap-2" aria-hidden>
      {actions.map(({ key, icon: Icon }) => (
        <li
          key={key}
          className="flex items-center gap-2.5 rounded-xl bg-slate-50 px-3 py-2.5 text-sm font-medium text-slate-700 ring-1 ring-hairline"
        >
          <Icon className="size-4 shrink-0 text-brand-600" />
          <span className="min-w-0 leading-tight">{t(key)}</span>
        </li>
      ))}
    </ul>
  );
}
