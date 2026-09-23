import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { t } from "@/i18n";
import "./globals.css";

// Self-hosted by next/font at build time: no request to Google from a member's
// phone, and no layout shift while it loads.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-dvh bg-canvas font-sans text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
