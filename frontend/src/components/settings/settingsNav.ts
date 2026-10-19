import type { MessageKey } from "@/i18n";

export interface SettingsPage {
  href: string;
  label: MessageKey;
  anyOf?: string[];
  ownerOnly?: boolean;
}

/** Settings, one page each (PLAN.md §16.2, 7.8). */
export const SETTINGS_PAGES: SettingsPage[] = [
  { href: "/staff/settings", label: "settings.nav.gym", anyOf: ["setup.gym"] },
  {
    href: "/staff/settings/plans",
    label: "settings.nav.plans",
    anyOf: ["setup.plans"],
  },
  {
    href: "/staff/settings/personal-training",
    label: "settings.nav.pt",
    anyOf: ["setup.plans"],
  },
  {
    href: "/staff/settings/payment-accounts",
    label: "settings.nav.payments",
    anyOf: ["setup.payment_methods"],
  },
  {
    href: "/staff/settings/branches",
    label: "settings.nav.branches",
    anyOf: ["setup.gym"],
  },
  {
    href: "/staff/settings/check-in",
    label: "settings.nav.checkIn",
    anyOf: ["setup.check_in_rules"],
  },
  {
    href: "/staff/settings/door",
    label: "settings.nav.door",
    anyOf: ["setup.devices"],
  },
  { href: "/staff/settings/security", label: "settings.nav.security", ownerOnly: true },
];
