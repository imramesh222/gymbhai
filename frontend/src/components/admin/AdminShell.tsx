"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Notice } from "@/components/Notice";
import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";

/** Platform admin (us): every gym, our prices, payments sent to us. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { me, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !me) router.replace("/staff/login");
  }, [loading, me, router]);

  if (loading || !me)
    return <p className="p-10 text-center text-slate-500">{t("common.loading")}</p>;
  if (!me.staff.is_platform_admin) {
    return (
      <div className="p-8">
        <Notice tone="error">{t("admin.only")}</Notice>
      </div>
    );
  }
  const links = [
    { href: "/admin", label: t("admin.gyms") },
    { href: "/admin/plans", label: t("admin.plans") },
  ];
  return (
    <div className="min-h-dvh">
      {/* Dark, so nobody confuses our console with a gym's dashboard. */}
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <span className="flex items-center gap-2.5">
            <LogoMark className="size-8" />
            <span className="font-semibold tracking-tight">{t("admin.title")}</span>
          </span>
          <nav className="flex items-center gap-1 text-sm">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={pathname === link.href ? "page" : undefined}
                className={`rounded-lg px-3 py-1.5 font-medium transition ${
                  pathname === link.href
                    ? "bg-white/10 text-white"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <button
              type="button"
              onClick={async () => {
                await signOut();
                router.replace("/staff/login");
              }}
              className="rounded-lg px-3 py-1.5 font-medium text-slate-300 transition hover:bg-white/5 hover:text-white"
            >
              {t("common.signOut")}
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">{children}</main>
    </div>
  );
}
