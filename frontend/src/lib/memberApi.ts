/** The member app's API (PLAN.md §8 "Member app"). */
import type { Locale } from "@/i18n";
import type {
  FreezeRequest,
  MemberMe,
  MemberSignIn,
  Notice,
  Payment,
  PaymentMethodAccount,
  PaymentRequest,
  Plan,
  PublicGym,
  PushStatus,
  ReceiptLink,
} from "@shared/types";
import { createClient } from "./api";

export type {
  MemberMe,
  MemberSignIn,
  PaymentRequest,
  PublicGym,
  PushStatus,
} from "@shared/types";





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
