/**
 * Where the language on screen is kept between visits (PLAN.md §16.6). Plain
 * constants, for the server's root layout and the browser's LocaleProvider
 * alike: a "use client" module can't hand values to a server component.
 */
export const LOCALE_COOKIE = "gb_locale";
export const DIGITS_COOKIE = "gb_digits";
