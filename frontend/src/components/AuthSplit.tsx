import Link from "next/link";

import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";

/**
 * Sign-up and staff sign-in: a gym photo with a short message on one side,
 * the form on the other. The photo stays put while a long form scrolls, and
 * is for wide screens only: a phone gets the form alone.
 */
export function AuthSplit({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-surface lg:grid lg:grid-cols-2">
      <aside className="relative hidden lg:block">
        <div className="sticky top-0 h-dvh overflow-hidden bg-slate-900">
          {/* Decorative: the message beside it says what matters. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/auth/gym.jpg"
            alt=""
            className="absolute inset-0 size-full object-cover"
          />
          <div
            aria-hidden
            className="absolute inset-0 bg-linear-to-t from-slate-950/90 via-slate-950/30 to-slate-950/50"
          />
          <p className="absolute top-8 left-10 flex items-center gap-2.5 xl:left-14">
            <LogoMark />
            <span className="text-lg font-bold tracking-tight text-white">
              {t("app.name")}
            </span>
          </p>
          <div className="absolute inset-x-0 bottom-0 p-10 xl:p-14">
            <p className="max-w-lg text-4xl leading-tight font-bold tracking-tight text-balance text-white xl:text-5xl">
              {t("auth.photo.title")}
            </p>
            <p className="mt-4 max-w-md text-lg text-pretty text-white/85">
              {t("auth.photo.body")}
            </p>
          </div>
        </div>
      </aside>

      <main className="relative isolate flex min-h-dvh flex-col justify-center px-4 py-10 sm:px-8">
        {/* The brand glow, on a phone where there's no photo. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-72 bg-[radial-gradient(70%_70%_at_50%_0%,var(--color-brand-100),transparent)] lg:hidden"
        />
        <div className="mx-auto w-full max-w-md">
          <Link href="/" className="mx-auto flex w-fit" aria-label={t("app.name")}>
            <LogoMark className="size-12" />
          </Link>
          <h1 className="mt-5 text-center text-3xl font-bold tracking-tight text-balance text-slate-900">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-2 text-center text-pretty text-slate-600">{subtitle}</p>
          )}
          {children}
        </div>
      </main>
    </div>
  );
}
