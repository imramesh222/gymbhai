"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RequireStaff } from "@/components/staff/RequireStaff";
import { SubscriptionBanner } from "@/components/staff/SubscriptionBanner";
import { LogoMark } from "@/components/ui/Logo";
import { t, type MessageKey } from "@/i18n";
import { paymentRequestsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface NavItem {
  href: string;
  label: MessageKey;
  // Shown if the staff member holds any of these; none means everyone.
  anyOf?: string[];
}

const NAV: NavItem[] = [
  { href: "/staff", label: "nav.today" },
  { href: "/staff/members", label: "nav.members", anyOf: ["members.view"] },
  { href: "/staff/expiring", label: "nav.expiring", anyOf: ["members.view"] },
  { href: "/staff/door", label: "nav.door", anyOf: ["door.check_in"] },
  {
    href: "/staff/payment-requests",
    label: "nav.requests",
    anyOf: ["payments.approve_app"],
  },
  { href: "/staff/payments", label: "nav.payments", anyOf: ["reports.money"] },
  { href: "/staff/attendance", label: "nav.attendance", anyOf: ["members.view"] },
  { href: "/staff/reports", label: "nav.reports", anyOf: ["reports.money"] },
  { href: "/staff/notices", label: "nav.notices", anyOf: ["messages.notices"] },
  { href: "/staff/sms", label: "nav.sms", anyOf: ["messages.sms"] },
  { href: "/staff/team", label: "nav.staff", anyOf: ["staff.manage"] },
  { href: "/staff/data", label: "nav.data", anyOf: ["members.view"] },
  { href: "/staff/subscription", label: "nav.subscription", anyOf: ["setup.gym"] },
  {
    href: "/staff/settings",
    label: "nav.settings",
    anyOf: [
      "setup.gym",
      "setup.plans",
      "setup.payment_methods",
      "setup.check_in_rules",
      "setup.reminders",
      "setup.devices",
      "memberships.extend_all",
    ],
  },
];

/** The red count on Payment requests (§5.4), checked every minute. */
function usePendingRequests(enabled: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const check = () =>
      paymentRequestsApi
        .count()
        .then((r) => !cancelled && setCount(r.pending))
        .catch(() => undefined);
    void check();
    const timer = setInterval(check, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);
  return count;
}

function Header() {
  const { me, signOut, can } = useAuth();
  const pending = usePendingRequests(can("payments.approve_app"));
  const router = useRouter();
  const pathname = usePathname();
  const items = NAV.filter((item) => !item.anyOf || item.anyOf.some(can));
  const isActive = (href: string) =>
    href === "/staff" ? pathname === "/staff" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-surface/85 backdrop-blur-md print:hidden">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 pt-3">
        <div className="flex min-w-0 items-center gap-3">
          <LogoMark className="size-9" />
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-900">
              {me?.gym?.name ?? t("app.name")}
            </p>
            <p className="truncate text-xs text-slate-500">{me?.staff.name}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 text-sm">
          <Link
            href="/staff/profile"
            className="rounded-lg px-2.5 py-1.5 font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
          >
            {t("nav.profile")}
          </Link>
          <button
            type="button"
            onClick={async () => {
              await signOut();
              router.replace("/staff/login");
            }}
            className="rounded-lg px-2.5 py-1.5 font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
          >
            {t("common.signOut")}
          </button>
        </div>
      </div>
      {/* Pills, and they scroll sideways on a phone: a gym with every
          permission ticked has fourteen of them. */}
      <nav className="no-scrollbar mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 pt-2 pb-2 lg:flex-wrap lg:overflow-x-visible">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(item.href) ? "page" : undefined}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              isActive(item.href)
                ? "bg-brand-600 text-white shadow-brand"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            {t(item.label)}
            {item.href === "/staff/payment-requests" && pending > 0 && (
              <span
                className={`ml-1.5 rounded-full px-1.5 py-0.5 text-xs font-bold ${
                  isActive(item.href)
                    ? "bg-white/20 text-white"
                    : "bg-red-600 text-white"
                }`}
              >
                {pending}
              </span>
            )}
          </Link>
        ))}
      </nav>
    </header>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireStaff>
      <Header />
      <SubscriptionBanner />
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8 print:max-w-none print:p-0">
        {children}
      </main>
    </RequireStaff>
  );
}
