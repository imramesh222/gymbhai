"use client";

/**
 * The member signed in to their gym's app.
 *
 * The last `me` (including the QR key) is kept on the phone, so the QR still
 * shows with no mobile data at the door (PLAN.md §4.2) — the one thing the
 * app must do offline. The session itself is the httpOnly refresh cookie.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { memberApi, memberClient, type MemberMe, type MemberSignIn } from "./memberApi";

const storageKey = (slug: string) => `gymbhai.member.${slug}`;

function remember(slug: string, me: MemberMe | null) {
  try {
    if (me) localStorage.setItem(storageKey(slug), JSON.stringify(me));
    else localStorage.removeItem(storageKey(slug));
  } catch {
    // Private browsing: the QR won't survive going offline, nothing worse.
  }
}

function recall(slug: string): MemberMe | null {
  try {
    const raw = localStorage.getItem(storageKey(slug));
    return raw ? (JSON.parse(raw) as MemberMe) : null;
  } catch {
    return null;
  }
}

interface MemberState {
  slug: string;
  me: MemberMe | null;
  loading: boolean;
  /** True when showing what was saved on the phone because we're offline. */
  offline: boolean;
  signedIn: (result: MemberSignIn) => void;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const Context = createContext<MemberState | null>(null);

export function MemberProvider({
  slug,
  children,
}: {
  slug: string;
  children: React.ReactNode;
}) {
  const [me, setMe] = useState<MemberMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const apply = useCallback(
    (next: MemberMe | null) => {
      setMe(next);
      remember(slug, next);
    },
    [slug],
  );

  const forget = useCallback(() => apply(null), [apply]);

  useEffect(() => {
    memberClient.setSessionLostHandler(forget);
    return () => memberClient.setSessionLostHandler(null);
  }, [forget]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let session;
      try {
        session = await memberClient.refreshSession();
      } catch {
        // No signal (or the server can't be reached): show what we had, QR
        // included. The member is signed out only if the server says so.
        if (cancelled) return;
        const saved = recall(slug);
        setMe(saved);
        setOffline(Boolean(saved));
        setLoading(false);
        return;
      }
      if (cancelled) return;
      if (session?.me && session.me.gym.slug === slug) {
        apply(session.me);
        setOffline(false);
      } else {
        forget();
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [slug, apply, forget]);

  const value = useMemo<MemberState>(
    () => ({
      slug,
      me,
      loading,
      offline,
      signedIn: (result) => {
        memberClient.setAccessToken(result.access_token);
        apply(result.me);
        setOffline(false);
      },
      refresh: async () => {
        try {
          apply(await memberApi.me());
          setOffline(false);
        } catch {
          // Keep what we have.
        }
      },
      signOut: async () => {
        await memberApi.logout().catch(() => undefined);
        memberClient.setAccessToken(null);
        forget();
      },
    }),
    [slug, me, loading, offline, apply, forget],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useMember(): MemberState {
  const context = useContext(Context);
  if (!context) throw new Error("useMember must be used inside MemberProvider");
  return context;
}
