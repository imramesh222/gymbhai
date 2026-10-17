"use client";

/**
 * Who is signed in. On first load the refresh cookie (if any) is swapped for
 * an access token, so a reload keeps the session without the token ever being
 * written to storage a script could read.
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

import {
  authApi,
  refreshSession,
  setAccessToken,
  setSessionLostHandler,
  type GymSignup,
  type Me,
  type Session,
} from "./api";

/** Signed in, or the password was right and a two-step code comes next. */
export type SignInResult = { me: Me } | { twoStepToken: string };

/** Must use two-step sign-in and hasn't set it up: only setting it up works. */
export function needsTwoStepSetup(me: Me): boolean {
  return me.two_step_required && !me.staff.two_step_enabled;
}

/** Where a signed-in account belongs. */
export function homeFor(me: Me): string {
  if (needsTwoStepSetup(me)) return "/staff/two-step";
  return me.staff.is_platform_admin ? "/admin" : "/staff";
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  signIn: (identifier: string, password: string) => Promise<SignInResult>;
  /** The code from the authenticator app (or a recovery code). */
  completeTwoStep: (twoStepToken: string, code: string) => Promise<Me>;
  registerGym: (payload: GymSignup) => Promise<Me>;
  signOut: () => Promise<void>;
  can: (permission: string) => boolean;
  /** Re-read the signed-in account and gym, e.g. after editing gym settings. */
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  // Bumped on sign-out: an answer to a request sent before it (a re-read of
  // the account still in flight) must not sign the person back in on screen.
  const generation = useRef(0);

  const apply = useCallback((session: Session) => {
    setAccessToken(session.access_token);
    setMe(session.me);
    return session.me;
  }, []);

  const forget = useCallback(() => {
    generation.current += 1;
    setAccessToken(null);
    setMe(null);
  }, []);

  useEffect(() => {
    setSessionLostHandler(forget);
    return () => setSessionLostHandler(null);
  }, [forget]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Keep trying while the network is down: "signed out" only when the
    // server says so, never because the Wi-Fi dropped for a moment.
    const attempt = (delay: number) => {
      refreshSession()
        .then((session) => {
          if (cancelled) return;
          if (session) apply(session);
          setLoading(false);
        })
        .catch(() => {
          if (!cancelled)
            timer = setTimeout(() => attempt(Math.min(delay * 2, 15_000)), delay);
        });
    };
    attempt(1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [apply]);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      signIn: async (identifier, password) => {
        const result = await authApi.login(identifier, password);
        if ("two_step_token" in result) return { twoStepToken: result.two_step_token };
        return { me: apply(result) };
      },
      completeTwoStep: async (twoStepToken, code) =>
        apply(await authApi.loginTwoStep(twoStepToken, code)),
      registerGym: async (payload) => apply(await authApi.registerGym(payload)),
      signOut: async () => {
        await authApi.logout().catch(() => undefined);
        forget();
      },
      can: (permission) => me?.permissions.includes(permission) ?? false,
      refreshMe: async () => {
        const asked = generation.current;
        const fresh = await authApi.me();
        if (asked === generation.current) setMe(fresh);
      },
    }),
    [me, loading, apply, forget],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
