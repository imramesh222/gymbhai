/**
 * English or Nepali (PLAN.md §16.6, §17.1): the member's language once
 * signed in (their own choice, else the gym's); before that, what they picked
 * on the sign-in screen, else the phone's language.
 *
 * Strings come from the shared catalogs through t(), which reads a module
 * setting. Changing language re-renders the whole app (the `key` below), so
 * no screen keeps text in the old language.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { getLocales } from "expo-localization";
import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { setLocale, type Digits, type Locale } from "@shared/i18n";

import { useMe } from "./hooks";

const CHOICE_KEY = "gymbhai.locale";

interface LocaleState {
  locale: Locale;
  /** Before signing in: the sign-in screen's English / नेपाली. */
  choose: (locale: Locale) => void;
}

const Context = createContext<LocaleState | null>(null);

function phoneLanguage(): Locale {
  return getLocales()[0]?.languageCode === "ne" ? "ne" : "en";
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const me = useMe().data;
  const [chosen, setChosen] = useState<Locale | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(CHOICE_KEY)
      .then((value) => {
        if (value === "en" || value === "ne") setChosen(value);
      })
      .catch(() => {});
  }, []);

  const locale: Locale = me?.language ?? chosen ?? phoneLanguage();
  const digits: Digits = me?.digits ?? "western";
  // Before children render, so their t() calls see it.
  setLocale(locale, digits);

  const value = useMemo<LocaleState>(
    () => ({
      locale,
      choose: (next) => {
        setChosen(next);
        AsyncStorage.setItem(CHOICE_KEY, next).catch(() => {});
      },
    }),
    [locale],
  );

  return (
    <Context.Provider value={value}>
      <Fragment key={`${locale}-${digits}`}>{children}</Fragment>
    </Context.Provider>
  );
}

export function useLocale(): LocaleState {
  const context = useContext(Context);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}
