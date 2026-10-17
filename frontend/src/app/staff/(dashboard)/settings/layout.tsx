"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { SETTINGS_PAGES } from "@/components/settings/settingsNav";
import { PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";

/** Settings: one page per subject, with a menu of them (PLAN.md §16.2, 7.8). */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const { can, me } = useAuth();
  const pathname = usePathname();
  const pages = SETTINGS_PAGES.filter((page) =>
    page.ownerOnly ? me?.staff.is_owner : page.anyOf?.some(can),
  );
  // The QR poster prints on its own, without the menu.
  if (pathname.startsWith("/staff/settings/poster")) return <>{children}</>;
  return (
    <div>
      <PageHeader title={t("nav.settings")} />
      <div className="flex flex-col gap-6 lg:flex-row">
        <nav
          aria-label={t("nav.settings")}
          className="no-scrollbar -mx-4 flex shrink-0 gap-1 overflow-x-auto px-4 lg:mx-0 lg:w-52 lg:flex-col lg:px-0 print:hidden"
        >
          {pages.map((page) => {
            const active = pathname === page.href;
            return (
              <Link
                key={page.href}
                href={page.href}
                aria-current={active ? "page" : undefined}
                className={`shrink-0 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-white text-brand-700 shadow-card ring-1 ring-hairline"
                    : "text-slate-600 hover:bg-white/70 hover:text-slate-900"
                }`}
              >
                {t(page.label)}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0 flex-1 space-y-4">{children}</div>
      </div>
    </div>
  );
}
