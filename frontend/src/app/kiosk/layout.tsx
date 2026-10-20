import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth";

// Installable, full screen, on the door's tablet (PLAN.md §19.2).
export const metadata: Metadata = { manifest: "/kiosk.webmanifest" };

/** Staff sign-in lives here, not on the root: the member app has its own. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
