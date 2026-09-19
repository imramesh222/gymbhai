"use client";

import { CheckInRulesSection, GymSection } from "@/components/settings/GymSection";
import {
  BranchesSection,
  ExtendEveryoneSection,
  PaymentMethodsSection,
  PlansSection,
} from "@/components/settings/ListSections";
import { DevicesSection } from "@/components/settings/DevicesSection";
import { RemindersSection } from "@/components/settings/RemindersSection";
import { PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { useAuth } from "@/lib/auth";

export default function SettingsPage() {
  const { me, can } = useAuth();
  const gym = me?.gym;
  if (!gym) return null;
  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.settings")} />
      {can("setup.gym") && <GymSection gym={gym} />}
      {can("setup.plans") && <PlansSection />}
      {can("setup.payment_methods") && <PaymentMethodsSection />}
      {can("setup.gym") && <BranchesSection />}
      {can("setup.reminders") && <RemindersSection />}
      {can("setup.check_in_rules") && <CheckInRulesSection gym={gym} />}
      {can("setup.devices") && <DevicesSection />}
      {can("memberships.extend_all") && <ExtendEveryoneSection />}
    </div>
  );
}
