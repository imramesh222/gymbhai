"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { t, type MessageKey } from "@/i18n";
import { MemberProvider, useMember } from "@/lib/memberSession";

import { SignIn } from "./SignIn";

/** Line icons, 24px grid, drawn in the current colour. */
const ICONS: Record<string, React.ReactNode> = {
  home: <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4v-5H9v5H5a1 1 0 0 1-1-1z" />,
  renew: <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4" />,
  payments: (
    <path d="M3 8h18M3 8v9a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8M3 8l2-3h14l2 3M7 14h4" />
  ),
  visits: (
    <path d="M8 3v3m8-3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z" />
  ),
  profile: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20a7 7 0 0 1 14 0" />,
};

const TABS: { path: string; label: MessageKey; icon: string }[] = [
  { path: "", label: "app.tab.home", icon: "home" },
  { path: "/renew", label: "app.tab.renew", icon: "renew" },
  { path: "/payments", label: "app.tab.payments", icon: "payments" },
  { path: "/visits", label: "app.tab.visits", icon: "visits" },
  { path: "/profile", label: "app.tab.profile", icon: "profile" },
];

function TabIcon({ name }: { name: string }) {
  return (
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
      {ICONS[name]}
    </svg>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  const { slug, me, loading, offline } = useMember();
  const pathname = usePathname();

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { scope: `/${slug}` })
        .catch(() => undefined);
    }
  }, [slug]);

  if (loading) {
    return (
      <p className="p-10 text-center text-sm text-slate-500">{t("common.loading")}</p>
    );
  }
  if (!me) return <SignIn />;

  const color = me.gym.brand_color ?? "#1d5fd1";
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col bg-canvas">
      {/* The gym's own colour, deepened towards the bottom, so the app feels
          like theirs and not like a dashboard. */}
      <header
        className="pt-safe rounded-b-3xl px-5 pb-6 text-white"
        style={{
          backgroundImage: `linear-gradient(140deg, ${color}, color-mix(in oklab, ${color} 62%, #0b1e42))`,
        }}
      >
        <div className="flex items-center gap-3">
          {me.gym.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={me.gym.logo_url}
              alt=""
              className="size-10 rounded-xl bg-white/95 object-contain p-1 ring-1 ring-white/30"
            />
          ) : (
            <span className="flex size-10 items-center justify-center rounded-xl bg-white/15 text-base font-bold ring-1 ring-white/25">
              {me.gym.name.trim()[0]?.toUpperCase()}
            </span>
          )}
          <div className="min-w-0">
            <p className="truncate text-lg font-semibold tracking-tight">
              {me.gym.name}
            </p>
            <p className="truncate text-sm text-white/70">{me.name}</p>
          </div>
        </div>
      </header>

      {offline && (
        <p className="mx-4 -mt-3 rounded-full bg-amber-100 px-4 py-1.5 text-center text-xs font-medium text-amber-900 shadow-card">
          {t("app.offline")}
        </p>
      )}

      <main className="flex-1 px-4 pt-5 pb-6">{children}</main>

      <nav className="pb-safe sticky bottom-0 grid grid-cols-5 border-t border-hairline bg-surface/95 backdrop-blur-md">
        {TABS.map((tab) => {
          const href = `/${slug}${tab.path}`;
          const active = pathname === href;
          return (
            <Link
              key={tab.path}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex flex-col items-center gap-1 pt-2.5 pb-2 text-[0.6875rem] font-medium transition ${
                active ? "" : "text-slate-400"
              }`}
              style={active ? { color } : undefined}
            >
              <TabIcon name={tab.icon} />
              {t(tab.label)}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function MemberShell({
  slug,
  children,
}: {
  slug: string;
  children: React.ReactNode;
}) {
  return (
    <MemberProvider slug={slug}>
      <Frame>{children}</Frame>
    </MemberProvider>
  );
}
