"use client";

import { useCallback, useEffect, useState } from "react";

import { CommandPalette, usePaletteShortcut } from "@/components/staff/CommandPalette";
import { BottomNav, PhoneTopBar, Sidebar } from "@/components/staff/Navigation";
import { RequireStaff } from "@/components/staff/RequireStaff";
import { SubscriptionBanner } from "@/components/staff/SubscriptionBanner";
import { UiProviders } from "@/components/ui/Providers";
import { freezeRequestsApi, openStaffLive, paymentRequestsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LiveProvider, useLive, type LiveType } from "@/lib/live";
import { useFollowLanguage } from "@/lib/locale";

/**
 * A count of what's waiting, for a menu badge (§5.4, §16.3 8.6): updated live
 * when a member sends one, and every few minutes in case the live stream
 * can't get through.
 */
function useWaiting(
  enabled: boolean,
  event: LiveType,
  count: () => Promise<{ pending: number }>,
): number {
  const [waiting, setWaiting] = useState(0);
  const [version, setVersion] = useState(0);
  useLive([event], () => setVersion((v) => v + 1));
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const check = () =>
      count()
        .then((r) => !cancelled && setWaiting(r.pending))
        .catch(() => undefined);
    void check();
    const timer = setInterval(check, 5 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled, version, count]);
  return waiting;
}

/**
 * A staff account or the gym's sign-in rules changed (permissions, disabled,
 * two-step sign-in required): re-read who is signed in, so the menu and the
 * screens follow at once. RequireStaff then sends anyone who must now set up
 * two-step sign-in to do that, and a disabled account is signed out.
 */
function StaffChanges() {
  const { refreshMe } = useAuth();
  useLive(["staff"], () => void refreshMe().catch(() => undefined));
  return null;
}

/** The menu (sidebar or phone bars), search, and the page itself. */
function Shell({ children }: { children: React.ReactNode }) {
  const { can, me } = useAuth();
  useFollowLanguage(me);
  const badges = {
    whatsNew: me?.changelog_unread ? 1 : 0,
    requests: useWaiting(
      can("payments.approve_app"),
      "payment_request",
      paymentRequestsApi.count,
    ),
    freezes: useWaiting(
      can("memberships.freeze"),
      "freeze_request",
      freezeRequestsApi.count,
    ),
  };
  const [searching, setSearching] = useState(false);
  const openSearch = useCallback(() => setSearching(true), []);
  usePaletteShortcut(openSearch);

  return (
    <div className="flex min-h-dvh">
      <Sidebar badges={badges} onSearch={openSearch} />
      <div className="flex min-w-0 flex-1 flex-col">
        <PhoneTopBar onSearch={openSearch} />
        <SubscriptionBanner />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-24 sm:pt-8 lg:px-8 lg:pb-10 print:max-w-none print:p-0">
          {children}
        </main>
      </div>
      <BottomNav badges={badges} />
      {searching && <CommandPalette onClose={() => setSearching(false)} />}
    </div>
  );
}

function Live({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  return (
    <LiveProvider open={me?.gym ? openStaffLive : null}>
      <StaffChanges />
      {children}
    </LiveProvider>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireStaff>
      <UiProviders>
        <Live>
          <Shell>{children}</Shell>
        </Live>
      </UiProviders>
    </RequireStaff>
  );
}
