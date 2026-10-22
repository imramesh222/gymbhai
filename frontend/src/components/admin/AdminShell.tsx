"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Notice } from "@/components/Notice";
import { LogoMark } from "@/components/ui/Logo";
import { t, type MessageKey } from "@/i18n";
import type { AdminPermission } from "@/lib/api";
import { needsTwoStepSetup, useAuth } from "@/lib/auth";

/**
 * Each page and what it needs (backend app/core/admin_permissions.py): the
 * gyms and their own account are for every admin.
 */
const PAGES: { href: string; label: MessageKey; permission?: AdminPermission }[] = [
  { href: "/admin", label: "admin.gyms" },
  { href: "/admin/plans", label: "admin.plans", permission: "admin.pricing" },
  { href: "/admin/apps", label: "admin.apps", permission: "admin.apps" },
  { href: "/admin/referrals", label: "referrals.title", permission: "admin.billing" },
  { href: "/admin/changelog", label: "changelog.title", permission: "admin.changelog" },
  { href: "/admin/admins", label: "admin.admins", permission: "admin.admins" },
  { href: "/admin/account", label: "nav.profile" },
];

/** Platform admin (us): every gym, our prices, payments sent to us. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { me, loading, signOut, can } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!me) router.replace("/staff/login");
    // Required for us, always (PLAN.md §16.1).
    else if (needsTwoStepSetup(me)) router.replace("/staff/two-step");
  }, [loading, me, router]);

  if (loading || !me || needsTwoStepSetup(me))
    return <p className="p-10 text-center text-slate-500">{t("common.loading")}</p>;
  if (!me.staff.is_platform_admin) {
    return (
      <div className="p-8">
        <Notice tone="error">{t("admin.only")}</Notice>
      </div>
    );
  }
  const allowed = (page: (typeof PAGES)[number]) =>
    !page.permission || can(page.permission);
  const links = PAGES.filter(allowed);
  const here = PAGES.find((page) => page.href === pathname);
  return (
    <div className="min-h-dvh">
      {/* Dark, so nobody confuses our console with a gym's dashboard. */}
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <span className="flex items-center gap-2.5">
            <LogoMark className="size-8" />
            <span className="font-semibold tracking-tight">{t("admin.title")}</span>
          </span>
          <nav className="flex flex-wrap items-center justify-end gap-1 text-sm">
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
                {t(link.label)}
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
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        {here && !allowed(here) ? (
          <Notice tone="error">{t("admin.notAllowed")}</Notice>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
