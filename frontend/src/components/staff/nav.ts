import {
  BarChart3,
  CalendarCheck,
  CalendarClock,
  ClipboardList,
  CreditCard,
  FileSpreadsheet,
  Inbox,
  LifeBuoy,
  LayoutDashboard,
  Megaphone,
  MessageSquare,
  PauseCircle,
  Receipt,
  ScanLine,
  Settings,
  Sparkles,
  UserCog,
  Users,
  Wallet,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { MessageKey } from "@/i18n";

/** A count beside a menu item: requests waiting for someone. */
export type Badge = "requests" | "freezes" | "whatsNew";
export type Badges = Partial<Record<Badge, number>>;

export interface NavItem {
  href: string;
  label: MessageKey;
  icon: LucideIcon;
  /** Shown if the staff member holds any of these; none means everyone. */
  anyOf?: string[];
  /** Carries the pending payment requests count. */
  badge?: Badge;
  /** For the phone's tab bar, where there is little room. */
  short?: MessageKey;
}

export interface NavGroup {
  label: MessageKey;
  items: NavItem[];
}

/** The staff dashboard's menu, in the groups of PLAN.md §16.2 (7.2). */
export const NAV: NavGroup[] = [
  {
    label: "nav.group.desk",
    items: [
      { href: "/staff", label: "nav.today", icon: LayoutDashboard },
      {
        href: "/staff/door",
        label: "nav.door",
        icon: ScanLine,
        anyOf: ["door.check_in"],
      },
      {
        href: "/staff/members",
        label: "nav.members",
        icon: Users,
        anyOf: ["members.view"],
      },
      {
        href: "/staff/enquiries",
        label: "nav.enquiries",
        icon: ClipboardList,
        anyOf: ["leads.manage"],
      },
      {
        href: "/staff/follow-up",
        label: "nav.followUp",
        icon: CalendarClock,
        anyOf: ["members.view"],
      },
      {
        href: "/staff/payment-requests",
        label: "nav.requests",
        icon: Inbox,
        anyOf: ["payments.approve_app"],
        badge: "requests",
        short: "nav.requestsShort",
      },
      {
        href: "/staff/freeze-requests",
        label: "nav.freezeRequests",
        icon: PauseCircle,
        anyOf: ["memberships.freeze"],
        badge: "freezes",
        short: "nav.freezeRequestsShort",
      },
    ],
  },
  {
    label: "nav.group.money",
    items: [
      {
        href: "/staff/payments",
        label: "nav.payments",
        icon: Wallet,
        anyOf: ["reports.money"],
      },
      {
        href: "/staff/expenses",
        label: "nav.expenses",
        icon: Receipt,
        // Recording alone shows the form, not the list (§18.1).
        anyOf: ["reports.money", "expenses.record"],
      },
      {
        href: "/staff/reports",
        label: "nav.reports",
        icon: BarChart3,
        anyOf: ["reports.money"],
      },
      {
        href: "/staff/attendance",
        label: "nav.attendance",
        icon: CalendarCheck,
        anyOf: ["members.view"],
      },
    ],
  },
  {
    label: "nav.group.messages",
    items: [
      {
        href: "/staff/notices",
        label: "nav.notices",
        icon: Megaphone,
        anyOf: ["messages.notices"],
      },
      {
        href: "/staff/automations",
        label: "nav.automations",
        icon: Zap,
        anyOf: ["setup.reminders"],
      },
      {
        href: "/staff/sms",
        label: "nav.sms",
        icon: MessageSquare,
        anyOf: ["messages.sms"],
      },
    ],
  },
  {
    label: "nav.group.gym",
    items: [
      {
        href: "/staff/team",
        label: "nav.staff",
        icon: UserCog,
        anyOf: ["staff.manage"],
      },
      {
        href: "/staff/data",
        label: "nav.data",
        icon: FileSpreadsheet,
        anyOf: ["members.view"],
      },
      {
        href: "/staff/settings",
        label: "nav.settings",
        icon: Settings,
        anyOf: [
          "setup.gym",
          "setup.plans",
          "setup.payment_methods",
          "setup.check_in_rules",
          "setup.devices",
          "memberships.extend_all",
        ],
      },
      {
        href: "/staff/subscription",
        label: "nav.subscription",
        icon: CreditCard,
        anyOf: ["setup.gym"],
      },
    ],
  },
  {
    label: "nav.group.help",
    items: [
      { href: "/staff/help", label: "nav.help", icon: LifeBuoy },
      {
        href: "/staff/whats-new",
        label: "nav.whatsNew",
        icon: Sparkles,
        badge: "whatsNew",
      },
    ],
  },
];

/** The phone's tab bar: the first four of these the person may open. */
export const PHONE_TABS = [
  "/staff",
  "/staff/members",
  "/staff/door",
  "/staff/payment-requests",
  "/staff/payments",
  "/staff/follow-up",
];

export function visibleNav(can: (permission: string) => boolean): NavGroup[] {
  return NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.anyOf || item.anyOf.some(can)),
  })).filter((group) => group.items.length > 0);
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/staff" ? pathname === "/staff" : pathname.startsWith(href);
}
