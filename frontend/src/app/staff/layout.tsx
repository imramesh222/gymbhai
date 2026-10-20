import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth";

// Installable from the Home Screen, which an iPhone needs before it gives the
// dashboard notifications (PLAN.md §18.6).
export const metadata: Metadata = {
  manifest: "/staff.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default" },
  icons: { apple: "/apple-touch-icon.png" },
};

/** Staff sign-in lives here, not on the root: the member app has its own. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
