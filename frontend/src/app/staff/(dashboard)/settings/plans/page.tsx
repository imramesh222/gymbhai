"use client";

import { PlanMonthsQuestion } from "@/components/settings/PlanMonthsQuestion";
import { PlansSection } from "@/components/settings/ListSections";
import { useGymCalendar } from "@/lib/gym";

export default function PlansSettingsPage() {
  // A new gym says how it counts months here, before its first sale (§5.1).
  const { calendar } = useGymCalendar();
  return (
    <div className="space-y-4">
      {!calendar && <PlanMonthsQuestion />}
      <PlansSection />
    </div>
  );
}
