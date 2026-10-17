"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/Button";
import { AuthShell } from "@/components/staff/AuthShell";
import { TwoStepSetup } from "@/components/staff/TwoStepSetup";
import { t } from "@/i18n";
import { homeFor, needsTwoStepSetup, useAuth } from "@/lib/auth";

/**
 * For an account that must use two-step sign-in and hasn't set it up: every
 * other screen sends it here, and the API refuses it everything else
 * (PLAN.md §16.1).
 */
export default function TwoStepRequiredPage() {
  const { me, loading, refreshMe, signOut } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!me) router.replace("/staff/login");
    else if (!needsTwoStepSetup(me)) router.replace(homeFor(me));
  }, [loading, me, router]);

  if (loading || !me || !needsTwoStepSetup(me)) {
    return (
      <p className="px-6 py-16 text-center text-sm text-slate-500">
        {t("common.loading")}
      </p>
    );
  }

  return (
    <AuthShell
      title={t("twoStep.requiredTitle")}
      footer={
        <Button
          variant="ghost"
          size="sm"
          onClick={async () => {
            await signOut();
            router.replace("/staff/login");
          }}
        >
          {t("common.signOut")}
        </Button>
      }
    >
      <p className="mt-2 text-sm text-slate-600">
        {me.staff.is_platform_admin
          ? t("twoStep.requiredAdmin")
          : t("twoStep.requiredGym", { gym: me.gym?.name ?? "" })}
      </p>
      <div className="mt-5">
        {/* Once it's on, the effect above takes them where they belong. */}
        <TwoStepSetup onDone={() => void refreshMe()} />
      </div>
    </AuthShell>
  );
}
