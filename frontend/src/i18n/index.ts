/**
 * All on-screen text goes through t() (CLAUDE.md). English only at launch;
 * Nepali later means adding ne.json, not touching screens.
 *
 * Keys are flat ("signup.title") so the type of every key is checked: a typo
 * or a missing string fails `tsc`, not a page in production.
 */
import en from "./en.json";

export type MessageKey = keyof typeof en;
type Catalog = Record<MessageKey, string>;

const catalogs: Record<string, Catalog> = { en };
const locale = "en";

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const template = catalogs[locale][key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

/** For keys built at runtime, such as `errors.${code}` from the API. */
export function isMessageKey(key: string): key is MessageKey {
  return key in catalogs[locale];
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
