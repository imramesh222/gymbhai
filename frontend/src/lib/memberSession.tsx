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
  useRef,
  useState,
} from "react";

import { pushOff } from "@/lib/push";
import { errorMessage } from "./api";
import { deskToken } from "./deskLink";
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
  /** The desk's QR opened this page and didn't work (expired, used). */
  deskError: string | null;
  signedIn: (result: MemberSignIn) => void;
  /** Sign in with the token in the desk's QR (PLAN.md §18.4). */
  signInAtDesk: (token: string) => Promise<void>;
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
  const [deskError, setDeskError] = useState<string | null>(null);
  const deskRun = useRef<Promise<void> | null>(null);

  const apply = useCallback(
    (next: MemberMe | null) => {
      setMe(next);
      remember(slug, next);
    },
    [slug],
  );

  const forget = useCallback(() => apply(null), [apply]);

  const signInAtDesk = useCallback(
    async (token: string) => {
      // A phone someone else signed in on (a family's): their reminders must
      // stop coming here before the next person's start.
      if (recall(slug)) {
        await pushOff(slug);
        await memberApi.logout().catch(() => undefined);
      }
      const result = await memberApi.deskSignIn(slug, token);
      memberClient.setAccessToken(result.access_token);
      apply(result.me);
      setOffline(false);
      setDeskError(null);
    },
    [slug, apply],
  );

  useEffect(() => {
    memberClient.setSessionLostHandler(forget);
    return () => memberClient.setSessionLostHandler(null);
  }, [forget]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Opened from the desk's QR (§18.4). The token leaves the address at
      // once: it isn't kept in the history, or in a link shared from here.
      const token = deskToken(window.location.href);
      if (token) {
        window.history.replaceState(
          window.history.state,
          "",
          window.location.pathname + window.location.search,
        );
        deskRun.current = signInAtDesk(token);
      }
      // Kept in a ref: a second run of this effect (React's dev mode) finds
      // the token gone from the address and waits for the same sign-in.
      if (deskRun.current) {
        try {
          await deskRun.current;
          if (cancelled) return;
          deskRun.current = null;
          setLoading(false);
          return;
        } catch (err) {
          if (cancelled) return;
          deskRun.current = null;
          // On to whoever this phone had signed in, if anyone.
          setDeskError(errorMessage(err));
        }
      }
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
  }, [slug, apply, forget, signInAtDesk]);

  const value = useMemo<MemberState>(
    () => ({
      slug,
      me,
      loading,
      offline,
      deskError,
      signInAtDesk,
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
        // A shared phone: the next member must not get this one's reminders.
        await pushOff(slug);
        await memberApi.logout().catch(() => undefined);
        memberClient.setAccessToken(null);
        forget();
      },
    }),
    [slug, me, loading, offline, deskError, signInAtDesk, apply, forget],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useMember(): MemberState {
  const context = useContext(Context);
  if (!context) throw new Error("useMember must be used inside MemberProvider");
  return context;
}
