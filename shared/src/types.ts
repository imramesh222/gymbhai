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
}

export interface Payment {
  id: string;
  member_id: string;
  membership_id: string | null;
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
}

export interface MemberSignIn {
  access_token: string | null;
  expires_in: number | null;
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
