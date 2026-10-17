import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Devanagari } from "next/font/google";
import { cookies } from "next/headers";
import { connection } from "next/server";

import { t } from "@/i18n";
import { DIGITS_COOKIE, LOCALE_COOKIE } from "@/i18n/cookies";
import { LocaleProvider } from "@/lib/locale";
import "./globals.css";

// Self-hosted by next/font at build time: no request to Google from a member's
// phone, and no layout shift while it loads.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Nepali (PLAN.md §16.6): Devanagari from its own font, after Inter's Latin.
const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-devanagari",
  display: "swap",
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
