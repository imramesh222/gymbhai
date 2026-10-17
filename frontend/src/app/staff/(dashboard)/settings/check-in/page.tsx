"use client";

import { CheckInRulesSection } from "@/components/settings/GymSection";
import { useAuth } from "@/lib/auth";

export default function CheckInSettingsPage() {
  const { me } = useAuth();
  return me?.gym ? <CheckInRulesSection gym={me.gym} /> : null;
}
