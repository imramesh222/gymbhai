"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RequireStaff } from "@/components/staff/RequireStaff";
import { SubscriptionBanner } from "@/components/staff/SubscriptionBanner";
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
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white print:hidden">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 pt-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-brand-900">
            {me?.gym?.name ?? t("app.name")}
          </p>
          <p className="truncate text-xs text-slate-500">{me?.staff.name}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1 text-sm">
          <Link
            href="/staff/profile"
            className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100"
          >
            {t("nav.profile")}
          </Link>
          <button
            type="button"
            onClick={async () => {
              await signOut();
              router.replace("/staff/login");
            }}
            className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100"
          >
            {t("common.signOut")}
          </button>
        </div>
      </div>
      <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2 pt-2">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
              isActive(item.href)
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t(item.label)}
            {item.href === "/staff/payment-requests" && pending > 0 && (
              <span className="ml-1.5 rounded-full bg-red-600 px-1.5 py-0.5 text-xs font-bold text-white">
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
      <main className="mx-auto max-w-6xl px-4 py-6 print:max-w-none print:p-0">
        {children}
      </main>
    </RequireStaff>
  );
}
