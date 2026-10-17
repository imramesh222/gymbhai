import Link from "next/link";

import { LanguageSwitch } from "@/components/LanguageSwitch";

import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import { LegalLinks } from "@/components/legal/LegalLinks";

/** The frame around staff sign-in, forgot password and two-step sign-in. */
export function AuthShell({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="relative isolate flex min-h-dvh flex-col justify-center px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-[radial-gradient(70%_70%_at_50%_0%,var(--color-brand-200),transparent)] opacity-70"
      />
      <div className="mx-auto w-full max-w-sm">
        <Link href="/" className="mx-auto flex w-fit items-center gap-2.5">
          <LogoMark />
          <span className="text-lg font-bold tracking-tight text-slate-900">
            {t("app.name")}
          </span>
        </Link>
        <div className="mt-6 rounded-2xl bg-surface p-6 shadow-raised ring-1 ring-hairline">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
          {children}
        </div>
        {footer && (
          <div className="mt-5 text-center text-sm text-slate-600">{footer}</div>
        )}
        <div className="mt-6 flex justify-center">
          <LanguageSwitch />
        </div>
        <LegalLinks />
      </div>
    </main>
  );
}
