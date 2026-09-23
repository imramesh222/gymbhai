import Link from "next/link";

import { LogoMark } from "@/components/ui/Logo";
import { t, type MessageKey } from "@/i18n";

const FEATURES: { key: string; icon: React.ReactNode }[] = [
  {
    key: "members",
    icon: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 20a8 8 0 0 1 16 0" />,
  },
  {
    key: "reminders",
    icon: <path d="M6 9a6 6 0 1 1 12 0c0 4 2 5 2 5H4s2-1 2-5ZM10 19a2 2 0 0 0 4 0" />,
  },
  {
    key: "door",
    icon: <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2m4 0h-2m0 2v4h-4v-2" />,
  },
];

export default function Home() {
  return (
    <main className="relative isolate min-h-dvh overflow-hidden">
      {/* A wash of brand colour behind the fold, not a flat block. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-40 h-[32rem] bg-[radial-gradient(60%_60%_at_50%_0%,var(--color-brand-200),transparent)] opacity-70"
      />

      <div className="mx-auto max-w-5xl px-6 pt-10 pb-16">
        <header className="flex items-center justify-between">
          <span className="flex items-center gap-2.5">
            <LogoMark />
            <span className="text-lg font-bold tracking-tight text-slate-900">
              {t("app.name")}
            </span>
          </span>
          <Link
            href="/staff/login"
            className="rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-700 transition hover:bg-white hover:shadow-card"
          >
            {t("home.signIn")}
          </Link>
        </header>

        <section className="mx-auto max-w-2xl pt-16 text-center sm:pt-24">
          <p className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-card ring-1 ring-hairline">
            <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
            {t("home.trial")}
          </p>
          <h1 className="mt-5 text-4xl font-bold tracking-tight text-balance text-slate-900 sm:text-5xl">
            {t("app.tagline")}
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-pretty text-slate-600">
            {t("home.pitch")}
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link
              href="/signup"
              className="rounded-xl bg-brand-600 px-6 py-3.5 text-center font-semibold text-white shadow-brand transition hover:bg-brand-700 active:translate-y-px"
            >
              {t("home.signUp")}
            </Link>
            <Link
              href="/staff/login"
              className="rounded-xl bg-white px-6 py-3.5 text-center font-semibold text-slate-800 shadow-card ring-1 ring-hairline transition hover:bg-slate-50 active:translate-y-px"
            >
              {t("home.signIn")}
            </Link>
          </div>
        </section>

        <section className="mt-20 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <div
              key={feature.key}
              className="rounded-2xl bg-surface p-5 shadow-card ring-1 ring-hairline"
            >
              <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="size-5"
                  aria-hidden
                >
                  {feature.icon}
                </svg>
              </span>
              <h2 className="mt-4 font-semibold text-slate-900">
                {t(`home.feature.${feature.key}.title` as MessageKey)}
              </h2>
              <p className="mt-1.5 text-sm text-slate-600">
                {t(`home.feature.${feature.key}.body` as MessageKey)}
              </p>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
