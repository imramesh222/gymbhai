"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Notice } from "@/components/Notice";
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
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <p className="font-semibold">{t("admin.title")}</p>
          <nav className="flex gap-4 text-sm">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={
                  pathname === link.href ? "font-semibold underline" : "text-slate-300"
                }
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
              className="text-slate-300"
            >
              {t("common.signOut")}
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
