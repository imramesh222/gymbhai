import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { cookies } from "next/headers";
import { connection } from "next/server";

import { t } from "@/i18n";
import { DIGITS_COOKIE, LOCALE_COOKIE } from "@/i18n/cookies";
import { LocaleProvider } from "@/lib/locale";
import "./globals.css";

// Served from our own origin: no request to Google from a member's phone, and
// no layout shift while it loads. The files come from npm (@fontsource-
// variable), not from Google at build time: next/font/google fails builds now
// and then when the download hiccups.
const inter = localFont({
  src: "../../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  weight: "100 900",
  variable: "--font-inter",
  display: "swap",
});

// Nepali (PLAN.md §16.6): Devanagari from its own font, after Inter's Latin.
const devanagari = localFont({
  src: "../../node_modules/@fontsource-variable/noto-sans-devanagari/files/noto-sans-devanagari-devanagari-wght-normal.woff2",
  weight: "100 900",
  variable: "--font-devanagari",
  display: "swap",
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0900-097F, U+1CD0-1CF9, U+200C-200D, U+20A8, U+20B9, U+20F0, U+25CC, U+A830-A839, U+A8E0-A8FF, U+11B00-11B09",
    },
  ],
});

export const metadata: Metadata = {
  title: { default: t("app.name"), template: `%s · ${t("app.name")}` },
  description: t("app.tagline"),
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1d5fd1",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Every page is rendered per request, so its scripts carry that request's
  // CSP nonce (src/proxy.ts). They are live dashboards anyway.
  await connection();
  const jar = await cookies();
  const locale = jar.get(LOCALE_COOKIE)?.value === "ne" ? "ne" : "en";
  const digits = jar.get(DIGITS_COOKIE)?.value === "nepali" ? "nepali" : "western";
  return (
    <html lang={locale} className={`${inter.variable} ${devanagari.variable}`}>
      <body className="min-h-dvh bg-canvas font-sans text-slate-900 antialiased">
        <LocaleProvider initial={{ locale, digits }}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
