/** The member app's API (PLAN.md §8 "Member app"). */
import {
  createClient,
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
  };
  qr: QrIdentity;
  gym: PublicGym;
  visits_this_month: number;
  streak_weeks: number;
  latest_notice: Notice | null;
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
  logout: () => request<void>("/api/v1/m/auth/logout", post()),
  me: () => request<MemberMe>("/api/v1/m/me"),
  payments: () =>
    request<{ dues: number; payments: Payment[]; requests: PaymentRequest[] }>(
      "/api/v1/m/me/payments",
    ),
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
  withdraw: (id: string) =>
    request<PaymentRequest>(`/api/v1/m/payment-requests/${id}/withdraw`, post()),
};
