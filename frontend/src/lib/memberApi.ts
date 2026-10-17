/** The member app's API (PLAN.md §8 "Member app"). */
import type { Digits, Locale } from "@/i18n";
import type { AccessWindow } from "@/lib/accessHours";
import type { ReceiptLink } from "@/lib/receiptShare";
import {
  createClient,
  type FreezeRequest,
  type Notice,
  type Payment,
  type PaymentMethodAccount,
  type Plan,
} from "./api";
import type { QrIdentity } from "./memberQr";

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

const client = createClient<MemberSignIn>({ refreshPath: "/api/v1/m/auth/refresh" });
export const memberClient = client;
const { request } = client;

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

/** PLAN.md §16.3, 8.3. No public key: push isn't set up on this server. */
export interface PushStatus {
  public_key: string | null;
  subscribed: boolean;
}

export const memberApi = {
  gym: (slug: string) =>
    request<PublicGym>(`/api/v1/m/${encodeURIComponent(slug)}/gym`),
  requestCode: (slug: string, who: { phone?: string; email?: string }) =>
    request<{ channel: "sms" | "email"; sent_to: string; expires_in: number }>(
      `/api/v1/m/${encodeURIComponent(slug)}/otp/request`,
      post(who),
    ),
  verifyCode: (
    slug: string,
    body: { phone?: string; email?: string; code: string; member_id?: string },
  ) =>
    request<MemberSignIn>(
      `/api/v1/m/${encodeURIComponent(slug)}/otp/verify`,
      post(body),
    ),
  joinOptions: (slug: string) =>
    request<{ plans: { id: string; name: string; price: number | null }[] }>(
      `/api/v1/m/${encodeURIComponent(slug)}/join`,
    ),
  askToJoin: (
    slug: string,
    body: {
      name: string;
      phone: string;
      email?: string | null;
      plan_id?: string | null;
      branch_id?: string | null;
      source?: string;
      message?: string | null;
    },
  ) =>
    request<{ received: boolean }>(
      `/api/v1/m/${encodeURIComponent(slug)}/join`,
      post(body),
    ),
  logout: () => request<void>("/api/v1/m/auth/logout", post()),
  pushStatus: (endpoint?: string) =>
    request<PushStatus>(
      `/api/v1/m/me/push${endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : ""}`,
    ),
  pushOn: (subscription: PushSubscriptionJSON) =>
    request<PushStatus>(
      "/api/v1/m/me/push",
      post({ endpoint: subscription.endpoint, keys: subscription.keys }),
    ),
  pushOff: (endpoint: string) =>
    request<PushStatus>("/api/v1/m/me/push/off", post({ endpoint })),
  me: () => request<MemberMe>("/api/v1/m/me"),
  payments: () =>
    request<{ dues: number; payments: Payment[]; requests: PaymentRequest[] }>(
      "/api/v1/m/me/payments",
    ),
  receiptLink: (paymentId: string) =>
    request<ReceiptLink>(`/api/v1/m/me/payments/${paymentId}/receipt-link`, post()),
  visits: (month?: string) =>
    request<{ at: string; result: string; branch_name: string | null }[]>(
      `/api/v1/m/me/visits${month ? `?month=${month}` : ""}`,
    ),
  notices: () => request<Notice[]>("/api/v1/m/notices"),
  renewOptions: () =>
    request<{
      plans: Plan[];
      payment_methods: PaymentMethodAccount[];
      renewal_starts_on: string;
      first_membership: boolean;
    }>("/api/v1/m/renew"),
  createRequest: (body: {
    plan_id: string;
    payment_method_id: string | null;
    amount: number;
    transaction_ref: string | null;
  }) => request<PaymentRequest>("/api/v1/m/payment-requests", post(body)),
  uploadScreenshot: (id: string, file: Blob) => {
    const form = new FormData();
    form.append("file", file, "screenshot.jpg");
    return request<PaymentRequest>(`/api/v1/m/payment-requests/${id}/screenshot`, {
      method: "POST",
      body: form,
    });
  },
  updateMe: (body: { emergency_contact?: string | null; language?: Locale | null }) =>
    request<MemberMe>("/api/v1/m/me", { ...post(body), method: "PATCH" }),
  changeEmail: (email: string) => request<void>("/api/v1/m/me/email", post({ email })),
  confirmEmail: (email: string, code: string) =>
    request<MemberMe>("/api/v1/m/me/email/confirm", post({ email, code })),
  uploadPhoto: (file: Blob) => {
    const form = new FormData();
    form.append("file", file, "photo.jpg");
    return request<MemberMe>("/api/v1/m/me/photo", { method: "POST", body: form });
  },
  latestFreeze: () => request<FreezeRequest | null>("/api/v1/m/freeze-requests/latest"),
  askToFreeze: (body: { from_date: string; to_date: string; reason: string }) =>
    request<FreezeRequest>("/api/v1/m/freeze-requests", post(body)),
  withdrawFreeze: (id: string) =>
    request<FreezeRequest>(`/api/v1/m/freeze-requests/${id}/withdraw`, post()),
  withdraw: (id: string) =>
    request<PaymentRequest>(`/api/v1/m/payment-requests/${id}/withdraw`, post()),
};

/** This member's live updates (backend/app/services/live.py). */
export const openMemberLive = (signal: AbortSignal) =>
  client.open("/api/v1/m/live", signal);
