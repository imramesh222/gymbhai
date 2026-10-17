"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GymSection } from "@/components/settings/GymSection";
import { SETTINGS_PAGES } from "@/components/settings/settingsNav";
import { useAuth } from "@/lib/auth";

/** Gym profile and calendar; anyone without it lands on the first page they may open. */
export default function SettingsPage() {
  const { me, can } = useAuth();
  const router = useRouter();
  const allowed = can("setup.gym");
  const first = SETTINGS_PAGES.find((page) =>
    page.ownerOnly ? me?.staff.is_owner : page.anyOf?.some(can),
  );
  useEffect(() => {
    if (!allowed && first) router.replace(first.href);
  }, [allowed, first, router]);
  if (!me?.gym || !allowed) return null;
  return <GymSection gym={me.gym} />;
}
