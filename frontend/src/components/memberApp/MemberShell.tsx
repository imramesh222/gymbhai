"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { t, type MessageKey } from "@/i18n";
import { MemberProvider, useMember } from "@/lib/memberSession";

import { SignIn } from "./SignIn";

const TABS: { path: string; label: MessageKey }[] = [
  { path: "", label: "app.tab.home" },
  { path: "/renew", label: "app.tab.renew" },
  { path: "/payments", label: "app.tab.payments" },
  { path: "/visits", label: "app.tab.visits" },
  { path: "/profile", label: "app.tab.profile" },
];

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
    <div className="mx-auto flex min-h-dvh max-w-md flex-col">
      <header
        className="flex items-center gap-3 px-4 py-3 text-white"
        style={{ background: color }}
      >
        {me.gym.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={me.gym.logo_url}
            alt=""
            className="size-8 rounded bg-white object-contain"
          />
        )}
        <p className="truncate font-semibold">{me.gym.name}</p>
      </header>
      {offline && (
        <p className="bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-900">
          {t("app.offline")}
        </p>
      )}
      <main className="flex-1 px-4 py-4">{children}</main>
      <nav className="sticky bottom-0 grid grid-cols-5 border-t border-slate-200 bg-white">
        {TABS.map((tab) => {
          const href = `/${slug}${tab.path}`;
          const active = pathname === href;
          return (
            <Link
              key={tab.path}
              href={href}
              className={`py-3 text-center text-xs font-medium ${active ? "text-brand-700" : "text-slate-500"}`}
              style={active ? { color } : undefined}
            >
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
