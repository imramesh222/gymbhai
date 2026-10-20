/**
 * The member app's API, as types (PLAN.md §8 "Member app", §17): one copy for
 * the web member app and the phone app. Money is integer paisa; dates are ISO
 * (YYYY-MM-DD) and times ISO 8601 in UTC.
 */
import type { AccessWindow } from "./accessHours";
import type { Digits, Locale } from "./i18n";
import type { QrIdentity } from "./qr/memberQr";

export type { AccessWindow, QrIdentity };

export type Method = "cash" | "esewa" | "khalti" | "fonepay" | "bank";

export type AccountKind = "esewa" | "khalti" | "fonepay" | "bank" | "other";

export interface Plan {
  id: string;
  name: string;
  duration_months: number | null;
  duration_days: number | null;
  price: number | null;
  admission_fee: number;
  all_branches: boolean;
  branch_ids: string[];
  is_active: boolean;
  sort_order: number;
  /** A visit pack (§16.4, 9.3); null is unlimited. */
  visit_limit: number | null;
  /** Off-peak hours (9.4); null is any time. */
  access_hours: AccessWindow[] | null;
  /** People one sale covers: 2 for a couple, up to 6 for a family (§19.1). */
  seats: number;
  /** The classes it lets one book (§19.4): none, all, or the chosen types. */
  classes?: "none" | "all" | "chosen";
  class_type_ids?: string[] | null;
}

export interface Payment {
  id: string;
  member_id: string;
  membership_id: string | null;
  /** Money for personal training (§18.3), not a membership. */
  pt_package_id: string | null;
  kind: "payment" | "refund";
  amount: number;
  method: Method;
  transaction_ref: string | null;
  paid_at: string;
  receipt_no: number;
  received_by: string | null;
  received_by_name: string | null;
  note: string | null;
  voided_at: string | null;
  void_reason: string | null;
}

export interface PaymentMethodAccount {
  id: string;
  kind: AccountKind;
  label: string;
  account_name: string | null;
  account_number: string | null;
  qr_image_url: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface Notice {
  id: string;
  branch_id: string | null;
  title: string;
  body: string;
  published_at: string;
  send_sms: boolean;
  sms_count: number;
  push_count: number;
}

export interface FreezeRequest {
  id: string;
  member_id: string;
  membership_id: string;
  from_date: string;
  to_date: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  reject_reason: string | null;
  created_at: string;
  reviewed_at: string | null;
  member_name: string | null;
  member_code: string | null;
  plan_name: string | null;
  ends_on: string | null;
  reviewed_by_name: string | null;
}

export interface PublicGym {
  slug: string;
  name: string;
  logo_url: string | null;
  brand_color: string | null;
  date_display: "ad" | "bs" | "both";
  branches: { id: string; name: string }[];
  join_form: boolean;
}

/** Personal training on the member's Home (§18.3): upcoming or under way. */
export interface MemberTraining {
  id: string;
  plan_name: string;
  kind: "monthly" | "sessions";
  status: "active" | "upcoming";
  trainer_name: string | null;
  start_date: string;
  end_date: string;
  /** A pack's size; null for monthly training. */
  sessions: number | null;
  sessions_left: number | null;
  days_left: number;
  /** Still to pay for it: its own, never in the membership's dues. */
  dues: number;
}

export interface MemberMe {
  id: string;
  name: string;
  member_code: string;
  phone: string;
  email: string | null;
  photo_url: string | null;
  home_branch_id: string;
  state: {
    status: "active" | "frozen" | "upcoming" | "expired" | "none";
    plan_name: string | null;
    valid_until: string | null;
    days_left: number;
    dues: number;
    visit_limit: number | null;
    visits_left: number | null;
    access_hours: AccessWindow[] | null;
    /** A family or couple plan (§19.1): the others on it. Missing from a
     * copy the phone app saved before these plans. */
    plan_with?: string[];
    /** Who pays for it, when someone else does. */
    paid_by?: string | null;
    /** Still owed on it by whoever pays. */
    group_dues?: number;
  };
  qr: QrIdentity;
  gym: PublicGym;
  visits_this_month: number;
  streak_weeks: number;
  latest_notice: Notice | null;
  emergency_contact: string | null;
  /** How busy their branch is now; null if hidden or too new to tell (8.5). */
  busy: "quiet" | "normal" | "busy" | null;
  /** The app's language: their own choice, else the gym's (§16.6). */
  language: Locale;
  own_language: Locale | null;
  digits: Digits;
  /** Missing from a copy the phone app saved before personal training. */
  training?: MemberTraining[];
  /** Classes at their branch in the next week: Home offers to book (§19.4). */
  has_classes?: boolean;
}

export interface MemberSignIn {
  access_token: string | null;
  expires_in: number | null;
  /** Only for the phone app, which keeps it in secure storage (§17.2). */
  refresh_token?: string | null;
  me: MemberMe | null;
  choose: { id: string; name: string }[] | null;
}

export interface PaymentRequest {
  id: string;
  plan_id: string;
  payment_method_id: string | null;
  amount: number;
  transaction_ref: string | null;
  screenshot_url: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  reject_reason: string | null;
  reviewed_at: string | null;
  membership_id: string | null;
  created_at: string;
  plan_name: string | null;
  method_label: string | null;
  member_id: string;
  member_name: string | null;
  member_code: string | null;
  expected_total: number | null;
  reviewed_by_name: string | null;
  /** A family or couple plan's others, renewed with the payer (§19.1). */
  with_names?: string[];
}

export interface PushStatus {
  public_key: string | null;
  subscribed: boolean;
}

export interface ReceiptLink {
  url: string;
  filename: string;
  text: string;
  expires_at: string;
}

/** What the member app's live updates say happened (§17.3). Ids only. */
export type MemberLiveType =
  | "member"
  | "payment_request"
  | "freeze_request"
  | "check_in"
  | "notice"
  | "class"
  | "resync";

export interface Visit {
  at: string;
  result: string;
  branch_name: string | null;
}

export interface MemberPayments {
  dues: number;
  payments: Payment[];
  requests: PaymentRequest[];
}

export interface RenewOptions {
  plans: Plan[];
  payment_methods: PaymentMethodAccount[];
  renewal_starts_on: string;
  first_membership: boolean;
  /** Whoever pays for a family or couple plan renews it for these too
   * (§19.1); plans for several are offered only then. */
  renew_with?: { id: string; name: string; first_membership: boolean }[];
}

/** A class in the member app's week (§19.4). */
export interface AppClass {
  id: string;
  type_name: string;
  color: string;
  starts_at: string;
  ends_at: string;
  instructor_name: string | null;
  places: number;
  places_left: number;
  waiting: number;
  cancelled: boolean;
  mine: "booked" | "waitlist" | null;
  booking_id: string | null;
  /** Why they can't book it: no_membership, plan_no_class, branch, frozen,
   * no_shows. */
  blocked: string | null;
}

export interface AppClasses {
  classes: AppClass[];
  booking_days: number;
  closes_minutes: number;
  cancel_hours: number;
  no_shows: number;
}

/** Progress (§19.5): whole numbers, as stored: grams, tenths of a percent, mm. */
export interface ProgressEntry {
  id: string;
  measured_on: string;
  weight_g: number | null;
  body_fat: number | null;
  chest_mm: number | null;
  waist_mm: number | null;
  hips_mm: number | null;
  arm_mm: number | null;
  thigh_mm: number | null;
  note: string | null;
  /** Staff who recorded it; null when the member did. */
  recorded_by_name: string | null;
  created_at: string;
}

export interface ProgressPhoto {
  id: string;
  taken_on: string;
  pose: "front" | "side" | "back";
  url: string;
  shared: boolean;
}

export interface Progress {
  height_mm: number | null;
  entries: ProgressEntry[];
  photos: ProgressPhoto[];
}

export type ProgressInput = Partial<
  Omit<ProgressEntry, "id" | "recorded_by_name" | "created_at">
>;

export interface JoinOptions {
  plans: { id: string; name: string; price: number | null }[];
}

export interface CodeSent {
  channel: "sms" | "email";
  sent_to: string;
  expires_in: number;
}

/** Where people hear about a gym (§16.4, 9.1); "walk_in" is the desk's. */
export const LEAD_SOURCES = [
  "walk_in",
  "phone",
  "facebook",
  "instagram",
  "tiktok",
  "referral",
  "other",
] as const;
export type LeadSource = (typeof LEAD_SOURCES)[number];
