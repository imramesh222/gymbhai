"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  useSyncExternalStore,
} from "react";

import { setLocale, type Digits, type Locale } from "@/i18n";
import { DIGITS_COOKIE, LOCALE_COOKIE } from "@/i18n/cookies";

/**
 * The language on screen (PLAN.md §16.6), kept in a cookie so the server knows
 * it on the next visit.
 *
 * The server renders English only: it serves many people at once, and the
 * language lives in one place in the module. So a Nepali page shows a blank
 * first frame on the server and in the browser alike (no mismatch when
 * React takes over), then renders in Nepali at once.
 */
const YEAR = 60 * 60 * 24 * 365;

interface LocaleState {
  locale: Locale;
  digits: Digits;
}

const Context = createContext<{
  locale: Locale;
  digits: Digits;
  change: (locale: Locale, digits?: Digits) => void;
} | null>(null);

const noop = () => () => undefined;

export function LocaleProvider({
  initial,
  children,
}: {
  initial: LocaleState;
  children: React.ReactNode;
}) {
  const [state, setState] = useState(initial);
  const browser = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
  if (browser) setLocale(state.locale, state.digits);

  const change = useCallback((locale: Locale, digits?: Digits) => {
    setState((now) => {
      const next = { locale, digits: digits ?? now.digits };
      if (next.locale === now.locale && next.digits === now.digits) return now;
      document.cookie = `${LOCALE_COOKIE}=${next.locale}; path=/; max-age=${YEAR}; samesite=lax`;
      document.cookie = `${DIGITS_COOKIE}=${next.digits}; path=/; max-age=${YEAR}; samesite=lax`;
      document.documentElement.lang = next.locale;
      setLocale(next.locale, next.digits);
      return next;
    });
  }, []);

  if (state.locale !== "en" && !browser) return <div className="min-h-dvh" aria-busy />;
  return (
    <Context.Provider value={{ ...state, change }}>
      {/* A new language: every screen renders again, with its new words. */}
      <div key={`${state.locale}-${state.digits}`} className="contents">
        {children}
      </div>
    </Context.Provider>
  );
}

const OUTSIDE = {
  locale: "en" as Locale,
  digits: "western" as Digits,
  change: () => undefined,
};

/** Outside a provider (a unit test): English, and switching does nothing. */
export function useLocale() {
  return useContext(Context) ?? OUTSIDE;
}

/** Follow the language the signed-in account has (own choice, else the gym's). */
export function useFollowLanguage(
  account: { language: Locale; digits: Digits } | null | undefined,
) {
  const { locale, digits, change } = useLocale();
  const wanted = account ? `${account.language}-${account.digits}` : null;
  const [applied, setApplied] = useState<string | null>(null);
  if (account && wanted !== applied) {
    setApplied(wanted);
    if (account.language !== locale || account.digits !== digits) {
      // After this render: a parent can't be updated while it renders.
      queueMicrotask(() => change(account.language, account.digits));
    }
  }
}
