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

interface AuthState {
  me: Me | null;
  loading: boolean;
  signIn: (identifier: string, password: string) => Promise<Me>;
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

  const apply = useCallback((session: Session) => {
    setAccessToken(session.access_token);
    setMe(session.me);
    return session.me;
  }, []);

  const forget = useCallback(() => {
    setAccessToken(null);
    setMe(null);
  }, []);

  useEffect(() => {
    setSessionLostHandler(forget);
    return () => setSessionLostHandler(null);
  }, [forget]);

  useEffect(() => {
    let cancelled = false;
    refreshSession()
      .then((session) => {
        if (!cancelled && session) apply(session);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apply]);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      signIn: async (identifier, password) =>
        apply(await authApi.login(identifier, password)),
      registerGym: async (payload) => apply(await authApi.registerGym(payload)),
      signOut: async () => {
        await authApi.logout().catch(() => undefined);
        forget();
      },
      can: (permission) => me?.permissions.includes(permission) ?? false,
      refreshMe: async () => setMe(await authApi.me()),
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
