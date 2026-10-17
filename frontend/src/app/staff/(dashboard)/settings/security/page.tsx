"use client";

import { SecuritySection } from "@/components/settings/GymSection";
import { useAuth } from "@/lib/auth";

export default function SecuritySettingsPage() {
  const { me } = useAuth();
  return me?.gym && me.staff.is_owner ? <SecuritySection gym={me.gym} /> : null;
}
