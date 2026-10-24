"use client";

import {
  ArrowRight,
  BellRing,
  CalendarDays,
  ChartColumnBig,
  Check,
  Languages,
  ShieldCheck,
  Smartphone,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  AppMock,
  ChartMock,
  HeroVisual,
  MembersMock,
  ScanChips,
  SmsMock,
  StaffMock,
} from "@/components/home/Mockups";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { LegalLinks } from "@/components/legal/LegalLinks";
import { LogoMark } from "@/components/ui/Logo";
import { localDigits, t, type MessageKey } from "@/i18n";

/*
 * The home page: what GymBhai is, for a gym owner deciding to try it.
 *
 * A client component, unlike most landing pages: the server renders English
 * only (lib/locale.tsx), so the Nepali page must be drawn in the browser.
 *
 * Photos are free ones from Unsplash, in public/home/: swap a file there to
 * change one (hero.jpg: photo-1571902943202, door.jpg: photo-1583454110551,
 * cta.jpg: photo-1574680096145). They sit under dark washes, so any gym
 * photo reads well; keep them under ~400 KB.
 */

const NEPAL: { key: string; icon: React.ElementType }[] = [
  { key: "dates", icon: CalendarDays },
  { key: "money", icon: Wallet },
  { key: "language", icon: Languages },
  { key: "reminders", icon: BellRing },
];

const STEPS = ["1", "2", "3"] as const;

/**
 * A link to a part of this page: a smooth scroll there (unless the visitor
 * asked for less motion), landing below the header (scroll-mt on the target).
 */
function Jump({
  to,
  className,
  children,
}: {
  to: string;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={`#${to}`}
      className={className}
      onClick={(event) => {
        const target = document.getElementById(to);
        if (!target) return;
        event.preventDefault();
        const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        target.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
        history.replaceState(null, "", `#${to}`);
      }}
    >
      {children}
    </a>
  );
}

/**
 * Stays at the top: clear over the photo, dark glass once the page moves, so
 * Features, How it works and Sign up are a tap away from anywhere. 4rem tall;
 * the hero starts below it, and anchors stop just below it (scroll-mt-20).
 */
function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-[background-color,box-shadow] duration-300 ${
        scrolled
          ? "bg-slate-950/85 shadow-[0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-lg"
          : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <LogoMark />
          <span className="text-lg font-bold tracking-tight text-white">
            {t("app.name")}
          </span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm font-medium text-white/70 md:flex">
          <Jump to="features" className="transition hover:text-white">
            {t("home.nav.features")}
          </Jump>
          <Jump to="how" className="transition hover:text-white">
            {t("home.nav.how")}
          </Jump>
        </nav>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="hidden sm:block">
            <LanguageSwitch dark />
          </div>
          <Link
            href="/staff/login"
            className="rounded-xl px-3 py-2 text-sm font-semibold text-white/85 transition hover:bg-white/10 hover:text-white"
          >
            {t("home.signIn")}
          </Link>
          <Link
            href="/signup"
            className="hidden rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-white/90 lg:inline-flex"
          >
            {t("home.signUp")}
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative isolate overflow-hidden bg-slate-950 text-white">
      {/* Decorative: the words over it say what matters. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/home/hero.jpg"
        alt=""
        fetchPriority="high"
        className="absolute inset-0 -z-30 size-full object-cover opacity-55"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-20 bg-linear-to-r from-slate-950 via-slate-950/85 to-slate-950/35"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-20 bg-linear-to-t from-slate-950 via-transparent to-slate-950/70"
      />
      <div
        aria-hidden
        className="absolute -top-48 right-[-10rem] -z-10 size-[42rem] rounded-full bg-brand-600/25 blur-3xl"
      />

      {/* Below the fixed header (4rem), then the same space as before. */}
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid items-center gap-12 pt-32 pb-24 sm:pt-36 lg:grid-cols-[1.15fr_0.85fr] lg:pt-40 lg:pb-32">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-xs font-semibold tracking-wide text-white/90 ring-1 ring-white/15 backdrop-blur">
              <span className="size-1.5 rounded-full bg-emerald-400" aria-hidden />
              {t("home.hero.eyebrow")}
            </p>
            <h1 className="mt-6 text-[2.75rem] leading-[1.04] font-bold tracking-tight text-balance sm:text-6xl lg:text-7xl">
              {t("home.hero.title")}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-pretty text-white/70">
              {t("home.hero.body")}
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/signup"
                className="group inline-flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-6 py-3.5 font-semibold text-white shadow-[0_12px_32px_-12px_rgba(58,112,238,0.9)] transition hover:bg-brand-400 active:translate-y-px"
              >
                {t("home.signUp")}
                <ArrowRight
                  className="size-4 transition group-hover:translate-x-0.5"
                  aria-hidden
                />
              </Link>
              <Jump
                to="how"
                className="inline-flex items-center justify-center rounded-xl bg-white/10 px-6 py-3.5 font-semibold text-white ring-1 ring-white/20 backdrop-blur transition hover:bg-white/15"
              >
                {t("home.seeHow")}
              </Jump>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/70">
              {(["home.trial", "home.hero.money", "home.hero.language"] as const).map(
                (key) => (
                  <li key={key} className="flex items-center gap-2">
                    <Check className="size-4 text-emerald-400" aria-hidden />
                    {t(key)}
                  </li>
                ),
              )}
            </ul>
            {/* On a phone the header has no room for it. */}
            <div className="mt-8 sm:hidden">
              <LanguageSwitch dark />
            </div>
          </div>
          <HeroVisual />
        </div>
      </div>
    </section>
  );
}

/** What makes it fit a gym in Nepal, lifted over the edge of the photo. */
function MadeForNepal() {
  return (
    <section className="relative z-10 mx-auto -mt-12 max-w-6xl px-4 sm:px-6">
      <div className="grid gap-px overflow-hidden rounded-3xl bg-slate-200 shadow-lifted ring-1 ring-hairline sm:grid-cols-2 lg:grid-cols-4">
        {NEPAL.map(({ key, icon: Icon }) => (
          <div key={key} className="bg-white p-6">
            <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
              <Icon className="size-5" aria-hidden />
            </span>
            <h2 className="mt-4 font-semibold text-slate-900">
              {t(`home.nepal.${key}.title` as MessageKey)}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-pretty text-slate-600">
              {t(`home.nepal.${key}.body` as MessageKey)}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * A section's title. It carries the anchor, not the section: a jump lands
 * on the words, below the header, instead of on the padding above them.
 */
function SectionHead({
  id,
  eyebrow,
  title,
  body,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div id={id} className="mx-auto max-w-3xl scroll-mt-20 text-center">
      <p className="text-sm font-semibold tracking-wide text-brand-700">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-bold tracking-tight text-balance text-slate-900 sm:text-4xl">
        {title}
      </h2>
      <p className="mt-3 text-lg text-pretty text-slate-600">{body}</p>
    </div>
  );
}

function Card({
  icon: Icon,
  name,
  className = "",
  children,
}: {
  icon: React.ElementType;
  name: string;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <article
      className={`flex flex-col gap-5 rounded-3xl bg-white p-6 shadow-card ring-1 ring-hairline ${className}`}
    >
      <div>
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
            <Icon className="size-5" aria-hidden />
          </span>
          <h3 className="text-lg font-semibold text-slate-900">
            {t(`home.feature.${name}.title` as MessageKey)}
          </h3>
        </div>
        <p className="mt-3 text-pretty text-slate-600">
          {t(`home.feature.${name}.body` as MessageKey)}
        </p>
      </div>
      {children}
    </article>
  );
}

function Features() {
  return (
    <section className="py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <SectionHead
          id="features"
          eyebrow={t("home.nav.features")}
          title={t("home.features.title")}
          body={t("home.features.body")}
        />
        <div className="mt-8 grid gap-4 lg:grid-cols-3">
          {/* The door: the reason the app exists, on a photo. */}
          <article className="relative isolate flex min-h-[28rem] flex-col justify-end gap-5 overflow-hidden rounded-3xl bg-slate-950 p-6 text-white lg:row-span-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/home/door.jpg"
              alt=""
              loading="lazy"
              className="absolute inset-0 -z-20 size-full object-cover object-[22%_50%] opacity-75"
            />
            <div
              aria-hidden
              className="absolute inset-0 -z-10 bg-linear-to-t from-slate-950 via-slate-950/75 to-slate-950/10"
            />
            <ScanChips />
            <div>
              <h3 className="text-2xl font-semibold tracking-tight">
                {t("home.feature.door.title")}
              </h3>
              <p className="mt-2 text-pretty text-white/75">
                {t("home.feature.door.body")}
              </p>
            </div>
          </article>

          <Card
            icon={Users}
            name="members"
            className="lg:col-span-2 lg:grid lg:grid-cols-2 lg:items-center"
          >
            <MembersMock />
          </Card>
          <Card icon={BellRing} name="reminders">
            <SmsMock />
          </Card>
          <Card icon={Smartphone} name="app">
            <AppMock />
          </Card>
          <Card
            icon={ChartColumnBig}
            name="reports"
            className="lg:col-span-2 lg:grid lg:grid-cols-2 lg:items-center"
          >
            <ChartMock />
          </Card>
          <Card icon={ShieldCheck} name="staff">
            <StaffMock />
          </Card>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <SectionHead
          id="how"
          eyebrow={t("home.nav.how")}
          title={t("home.how.title")}
          body={t("home.how.body")}
        />
        <ol className="relative mt-16 grid gap-10 md:grid-cols-3 md:gap-8">
          {/* The thread through the steps, on a wide screen. */}
          <div
            aria-hidden
            className="absolute top-6 right-[16%] left-[16%] hidden h-px bg-linear-to-r from-brand-200 via-brand-400 to-brand-200 md:block"
          />
          {STEPS.map((step) => (
            <li key={step} className="relative text-center">
              <span className="relative mx-auto flex size-12 items-center justify-center rounded-2xl bg-linear-to-br from-brand-500 to-brand-700 text-lg font-bold text-white shadow-brand">
                {localDigits(step)}
              </span>
              <h3 className="mt-6 text-lg font-semibold text-slate-900">
                {t(`home.how.${step}.title`)}
              </h3>
              <p className="mx-auto mt-2 max-w-xs text-pretty text-slate-600">
                {t(`home.how.${step}.body`)}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CallToAction() {
  return (
    <section className="relative isolate overflow-hidden bg-slate-950 py-24 text-white sm:py-32">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/home/cta.jpg"
        alt=""
        loading="lazy"
        className="absolute inset-0 -z-20 size-full object-cover object-[60%_30%] opacity-60"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-linear-to-r from-slate-950 via-slate-950/80 to-brand-950/30"
      />
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <h2 className="max-w-2xl text-4xl leading-tight font-bold tracking-tight text-balance sm:text-5xl">
          {t("home.cta.title")}
        </h2>
        <p className="mt-5 max-w-xl text-lg text-pretty text-white/75">
          {t("home.cta.body")}
        </p>
        <div className="mt-9 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/signup"
            className="group inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 font-semibold text-slate-900 transition hover:bg-white/90 active:translate-y-px"
          >
            {t("home.signUp")}
            <ArrowRight
              className="size-4 transition group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
          <Link
            href="/staff/login"
            className="inline-flex items-center justify-center rounded-xl px-6 py-3.5 font-semibold text-white ring-1 ring-white/25 transition hover:bg-white/10"
          >
            {t("home.signIn")}
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="mx-auto flex max-w-6xl flex-col items-center gap-5 px-4 py-12 sm:flex-row sm:justify-between sm:px-6">
      <div className="flex items-center gap-2.5">
        <LogoMark className="size-8" />
        <div>
          <p className="font-bold tracking-tight text-slate-900">{t("app.name")}</p>
          <p className="text-xs text-slate-500">{t("home.hero.eyebrow")}</p>
        </div>
      </div>
      <LanguageSwitch />
      <div className="[&>nav]:mt-0">
        <LegalLinks />
      </div>
    </footer>
  );
}

export default function Home() {
  return (
    <main className="min-h-dvh bg-canvas normal-nums">
      <SiteHeader />
      <Hero />
      <MadeForNepal />
      <Features />
      <HowItWorks />
      <CallToAction />
      <Footer />
    </main>
  );
}
