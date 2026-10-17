"use client";

import { DevicesCard } from "@/components/staff/DevicesCard";
import { TwoStepCard } from "@/components/staff/TwoStepCard";
import { PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";

/** Our own account: two-step sign-in, which every platform admin must use. */
export default function AdminAccountPage() {
  const { me } = useAuth();
  return (
    <div className="max-w-md space-y-4">
      <PageHeader
        title={t("nav.profile")}
        subtitle={me?.staff.email ?? me?.staff.phone ?? ""}
      />
      <TwoStepCard />
      <DevicesCard />
    </div>
  );
}
