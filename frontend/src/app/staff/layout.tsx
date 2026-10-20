import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth";

// Installable from the Home Screen, which an iPhone needs before it gives the
// dashboard notifications (PLAN.md §18.6). Its icons are the files in src/app
// (favicon.ico, icon.png, apple-icon.png), as on every page.
export const metadata: Metadata = {
  manifest: "/staff.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default" },
};

/** Staff sign-in lives here, not on the root: the member app has its own. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
