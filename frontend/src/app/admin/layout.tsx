import { AdminShell } from "@/components/admin/AdminShell";
import { UiProviders } from "@/components/ui/Providers";
import { AuthProvider } from "@/lib/auth";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <UiProviders>
        <AdminShell>{children}</AdminShell>
      </UiProviders>
    </AuthProvider>
  );
}
