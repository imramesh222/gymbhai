"use client";

import {
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  Menu as MenuIcon,
  Search,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";
import { useStoredFlag } from "@/lib/storedFlag";

import { PHONE_TABS, isActive, visibleNav, type Badges, type NavItem } from "./nav";

const COLLAPSED_KEY = "gb.sidebar.collapsed";

function Badge({
  count,
  active,
  dot,
}: {
  count: number;
  active?: boolean;
  /** Just "something new", no number (What's new). */
  dot?: boolean;
}) {
  if (count <= 0) return null;
  if (dot) {
    return (
      <span className="ml-auto size-2 rounded-full bg-red-600">
        <span className="sr-only">{t("nav.new")}</span>
      </span>
    );
  }
  return (
    <span
      className={`ml-auto rounded-full px-1.5 py-0.5 text-xs font-bold ${
        active ? "bg-white/20 text-white" : "bg-red-600 text-white"
      }`}
    >
      {count}
    </span>
  );
}

function useSignOut() {
  const { signOut } = useAuth();
  const router = useRouter();
  return async () => {
    await signOut();
    router.replace("/staff/login");
  };
}

/**
 * The laptop menu: a left sidebar in groups, filtered by permission. It can
 * fold down to icons; that choice is remembered on this device.
 */
export function Sidebar({
  badges,
  onSearch,
}: {
  badges: Badges;
  onSearch: () => void;
}) {
  const { me, can } = useAuth();
  const pathname = usePathname();
  const signOut = useSignOut();
  const [collapsed, setCollapsed] = useStoredFlag(COLLAPSED_KEY);
  const toggle = () => setCollapsed(!collapsed);

  const link = (item: NavItem) => {
    const active = isActive(pathname, item.href);
    const pending = item.badge ? (badges[item.badge] ?? 0) : 0;
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        aria-current={active ? "page" : undefined}
        title={collapsed ? t(item.label) : undefined}
        className={`relative flex items-center gap-3 rounded-xl px-3 py-1.5 text-sm font-medium transition ${
          active
            ? "bg-brand-600 text-white shadow-brand"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        } ${collapsed ? "justify-center px-0" : ""}`}
      >
        <Icon className="size-[1.125rem] shrink-0" aria-hidden />
        {collapsed ? (
          <span className="sr-only">{t(item.label)}</span>
        ) : (
          <>
            <span className="truncate">{t(item.label)}</span>
            {item.badge && (
              <Badge count={pending} active={active} dot={item.badge === "whatsNew"} />
            )}
          </>
        )}
        {collapsed && pending > 0 && (
          <span
            className="absolute top-1.5 right-3 size-2 rounded-full bg-red-600"
            aria-hidden
          />
        )}
      </Link>
    );
  };

  return (
    <aside
      className={`sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-hairline bg-surface transition-[width] lg:flex print:hidden ${
        collapsed ? "w-[4.5rem]" : "w-64"
      }`}
    >
      <div
        className={`flex items-center gap-3 px-4 pt-4 ${collapsed ? "justify-center px-0" : ""}`}
      >
        <LogoMark className="size-9 shrink-0" />
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-900">{me?.gym?.name}</p>
            <p className="truncate text-xs text-slate-500">{me?.staff.name}</p>
          </div>
        )}
      </div>
      <div className={`px-3 pt-4 ${collapsed ? "px-2" : ""}`}>
        <button
          type="button"
          onClick={onSearch}
          className={`flex w-full items-center gap-2 rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-500 transition hover:bg-slate-200/70 ${
            collapsed ? "justify-center px-0" : ""
          }`}
        >
          <Search className="size-4 shrink-0" aria-hidden />
          {collapsed ? (
            <span className="sr-only">{t("nav.search")}</span>
          ) : (
            <>
              <span className="flex-1 text-left">{t("nav.searchHint")}</span>
              <kbd className="rounded bg-white px-1.5 text-xs text-slate-500 ring-1 ring-hairline">
                ⌘K
              </kbd>
            </>
          )}
        </button>
      </div>
      <nav
        aria-label={t("nav.menu")}
        className="flex-1 space-y-4 overflow-y-auto px-3 py-3"
      >
        {visibleNav(can).map((group) => (
          <div key={group.label}>
            {!collapsed && (
              <p className="px-3 pb-1.5 text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
                {t(group.label)}
              </p>
            )}
            <div className="space-y-0.5">{group.items.map(link)}</div>
          </div>
        ))}
      </nav>
      <div className="space-y-0.5 border-t border-hairline px-3 py-3">
        {link({ href: "/staff/profile", label: "nav.profile", icon: UserRound })}
        <button
          type="button"
          onClick={() => void signOut()}
          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 ${
            collapsed ? "justify-center px-0" : ""
          }`}
        >
          <LogOut className="size-[1.125rem] shrink-0" aria-hidden />
          <span className={collapsed ? "sr-only" : ""}>{t("common.signOut")}</span>
        </button>
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 ${
            collapsed ? "justify-center px-0" : ""
          }`}
        >
          {collapsed ? (
            <ChevronsRight className="size-[1.125rem]" aria-hidden />
          ) : (
            <>
              <ChevronsLeft className="size-[1.125rem]" aria-hidden />
              {t("nav.collapse")}
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

/** The phone's header: the gym, search, and the menu of everything else. */
export function PhoneTopBar({ onSearch }: { onSearch: () => void }) {
  const { me } = useAuth();
  return (
    <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-hairline bg-surface/90 px-4 py-2.5 backdrop-blur-md lg:hidden print:hidden">
      <LogoMark className="size-8 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-slate-900">{me?.gym?.name}</p>
        <p className="truncate text-xs text-slate-500">{me?.staff.name}</p>
      </div>
      <button
        type="button"
        onClick={onSearch}
        aria-label={t("nav.search")}
        className="rounded-xl p-2 text-slate-600 hover:bg-slate-100"
      >
        <Search className="size-5" aria-hidden />
      </button>
    </header>
  );
}

/**
 * The phone's tab bar: the four screens the person uses most and may open,
 * then More, a sheet with the rest of the menu.
 */
export function BottomNav({ badges }: { badges: Badges }) {
  const { can } = useAuth();
  const pathname = usePathname();
  const signOut = useSignOut();
  const [more, setMore] = useState(false);
  const groups = visibleNav(can);
  const all = groups.flatMap((group) => group.items);
  const tabs = PHONE_TABS.map((href) => all.find((item) => item.href === href))
    .filter((item): item is NavItem => Boolean(item))
    .slice(0, 4);

  const tab = (item: NavItem) => {
    const active = isActive(pathname, item.href);
    const pending = item.badge ? (badges[item.badge] ?? 0) : 0;
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        aria-current={active ? "page" : undefined}
        className={`relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[0.6875rem] font-medium ${
          active ? "text-brand-700" : "text-slate-500"
        }`}
      >
        <Icon className="size-5" aria-hidden />
        {t(item.short ?? item.label)}
        {pending > 0 && (
          <span className="absolute top-1 left-1/2 ml-2 rounded-full bg-red-600 px-1.5 text-[0.625rem] font-bold text-white">
            {pending}
          </span>
        )}
      </Link>
    );
  };

  return (
    <>
      <nav
        aria-label={t("nav.menu")}
        className="pb-safe fixed inset-x-0 bottom-0 z-30 flex border-t border-hairline bg-surface/95 backdrop-blur-md lg:hidden print:hidden"
      >
        {tabs.map(tab)}
        <button
          type="button"
          onClick={() => setMore(true)}
          aria-expanded={more}
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[0.6875rem] font-medium text-slate-500"
        >
          <MenuIcon className="size-5" aria-hidden />
          {t("nav.more")}
        </button>
      </nav>
      {more && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 lg:hidden"
          onPointerDown={(event) =>
            event.target === event.currentTarget && setMore(false)
          }
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.more")}
            className="pb-safe absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-3xl bg-surface px-4 pt-3 shadow-lifted"
          >
            <div className="flex items-center justify-between pb-2">
              <span className="text-sm font-semibold text-slate-900">
                {t("nav.more")}
              </span>
              <button
                type="button"
                onClick={() => setMore(false)}
                aria-label={t("common.close")}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              >
                <X className="size-5" aria-hidden />
              </button>
            </div>
            {groups.map((group) => (
              <div key={group.label} className="pb-3">
                <p className="px-1 pb-1 text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
                  {t(group.label)}
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active = isActive(pathname, item.href);
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        onClick={() => setMore(false)}
                        className={`flex flex-col items-center gap-1.5 rounded-2xl px-2 py-3 text-center text-xs font-medium ${
                          active
                            ? "bg-brand-50 text-brand-700"
                            : "bg-slate-50 text-slate-700"
                        }`}
                      >
                        <Icon className="size-5" aria-hidden />
                        {t(item.label)}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
            <div className="flex gap-2 border-t border-hairline py-3">
              <Link
                href="/staff/profile"
                onClick={() => setMore(false)}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-50 py-2.5 text-sm font-medium text-slate-700"
              >
                <UserRound className="size-4" aria-hidden />
                {t("nav.profile")}
              </Link>
              <button
                type="button"
                onClick={() => void signOut()}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-50 py-2.5 text-sm font-medium text-slate-700"
              >
                <LogOut className="size-4" aria-hidden />
                {t("common.signOut")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
