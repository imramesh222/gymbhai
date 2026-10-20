/** The member app's API (PLAN.md §8 "Member app"). */
import type { Locale } from "@/i18n";
import type {
  AppClasses,
  Progress,
  ProgressInput,
  FreezeRequest,
  MemberMe,
  MemberSignIn,
  Notice,
  Payment,
  PaymentRequest,
  PublicGym,
  PushStatus,
  ReceiptLink,
  RenewOptions,
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
  /** The QR the desk showed (PLAN.md §18.4): signed in with no code. */
  deskSignIn: (slug: string, token: string) =>
    request<MemberSignIn>(
      `/api/v1/m/${encodeURIComponent(slug)}/desk-sign-in`,
      post({ token }),
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
  renewOptions: () => request<RenewOptions>("/api/v1/m/renew"),
  /** A week of classes at their branch (§19.4). */
  classes: (from?: string) =>
    request<AppClasses>(`/api/v1/m/classes${from ? `?from=${from}` : ""}`),
  /** A place or the waitlist; `key` makes a double tap one booking. */
  bookClass: (classId: string, key: string) =>
    request<AppClasses>(`/api/v1/m/classes/${classId}/book`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
    }),
  cancelClassBooking: (bookingId: string) =>
    request<AppClasses>(`/api/v1/m/class-bookings/${bookingId}/cancel`, post()),
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
  /** Their own progress (§19.5). */
  progress: () => request<Progress>("/api/v1/m/progress"),
  recordProgress: (body: ProgressInput, key: string) =>
    request<Progress>("/api/v1/m/progress", {
      ...post(body),
      headers: { "Idempotency-Key": key },
    }),
  updateProgress: (id: string, body: ProgressInput) =>
    request<Progress>(`/api/v1/m/progress/${id}`, { ...post(body), method: "PATCH" }),
  deleteProgress: (id: string) =>
    request<Progress>(`/api/v1/m/progress/${id}`, { method: "DELETE" }),
  setHeight: (height_mm: number | null) =>
    request<Progress>("/api/v1/m/progress/height", {
      ...post({ height_mm }),
      method: "PUT",
    }),
  addProgressPhoto: (file: Blob, pose: string) => {
    const form = new FormData();
    form.append("file", file, "progress.jpg");
    form.append("pose", pose);
    return request<Progress>("/api/v1/m/progress/photos", {
      method: "POST",
      body: form,
    });
  },
  shareProgressPhoto: (id: string, shared: boolean) =>
    request<Progress>(`/api/v1/m/progress/photos/${id}`, {
      ...post({ shared }),
      method: "PATCH",
    }),
  deleteProgressPhoto: (id: string) =>
    request<Progress>(`/api/v1/m/progress/photos/${id}`, { method: "DELETE" }),
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
