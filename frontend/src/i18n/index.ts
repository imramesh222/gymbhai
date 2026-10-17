/**
 * All on-screen text goes through t() (CLAUDE.md), in English or Nepali
 * (PLAN.md §16.6).
 *
 * Keys are flat ("signup.title") so the type of every key is checked: a typo
 * or a missing string fails `tsc`, not a page in production. ne.json must have
 * every key en.json has, with the same {placeholders} (index.test.ts).
 *
 * The server always renders English: one language for every request it is
 * handling at once. A Nepali page appears once the browser takes over
 * (LocaleProvider), from the same cookie.
 */
import en from "./en.json";
import ne from "./ne.json";

export type MessageKey = keyof typeof en;
type Catalog = Record<MessageKey, string>;
export type Locale = "en" | "ne";
export type Digits = "nepali" | "western";

const catalogs: Record<Locale, Catalog> = { en, ne: ne as Catalog };
let current: Locale = "en";
let nepaliDigits = false;

function active(): Locale {
  return typeof window === "undefined" ? "en" : current;
}

/** Called by LocaleProvider before the page renders. */
export function setLocale(locale: Locale, digits: Digits = "western"): void {
  current = locale;
  nepaliDigits = locale === "ne" && digits === "nepali";
}

export function getLocale(): Locale {
  return active();
}

const DEVANAGARI = "०१२३४५६७८९";

/** 2083 -> २०८३ when the gym shows Nepali digits; otherwise as it is. */
export function localDigits(text: string): string {
  if (!nepaliDigits || active() !== "ne") return text;
  return text.replace(/[0-9]/g, (d) => DEVANAGARI[Number(d)]);
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const template = catalogs[active()][key] ?? catalogs.en[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars
      ? typeof vars[name] === "number"
        ? localDigits(String(vars[name]))
        : String(vars[name])
      : match,
  );
}

/** For keys built at runtime, such as `errors.${code}` from the API. */
export function isMessageKey(key: string): key is MessageKey {
  return key in catalogs.en;
}

/** One or other form by count. English needs only two; Nepali the same. */
export function plural(
  count: number,
  one: MessageKey,
  other: MessageKey,
  vars?: Record<string, string | number>,
): string {
  return t(count === 1 ? one : other, { count, ...vars });
}
