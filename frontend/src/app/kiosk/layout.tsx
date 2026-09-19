import { AuthProvider } from "@/lib/auth";

/** Staff sign-in lives here, not on the root: the member app has its own. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
