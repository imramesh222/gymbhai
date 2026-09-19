"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";

/**
 * Keeps signed-out visitors out of the dashboard without flashing it first.
 * The redirect runs in an effect: navigating during render is dropped by React.
 */
export function RequireStaff({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) router.replace("/staff/login");
  }, [loading, me, router]);

  if (loading || !me) {
    return (
      <p className="px-6 py-16 text-center text-sm text-slate-500">
        {t("common.loading")}
      </p>
    );
  }
  return <>{children}</>;
}
