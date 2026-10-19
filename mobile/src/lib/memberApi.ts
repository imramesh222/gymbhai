/** The member app's API (PLAN.md §8 "Member app", §17), as the phone calls it. */
import type { Locale } from "@shared/i18n";
import type {
  CodeSent,
  FreezeRequest,
  JoinOptions,
  LeadSource,
  MemberMe,
  MemberPayments,
  MemberSignIn,
  Notice,
  PaymentRequest,
  PublicGym,
  PushStatus,
  ReceiptLink,
  RenewOptions,
  Visit,
} from "@shared/types";

import { request } from "./api";

const gymPath = (slug: string, rest: string) =>
  `/api/v1/m/${encodeURIComponent(slug)}${rest}`;

/** A picked image, as React Native's fetch uploads it. */
export interface UploadFile {
  uri: string;
  name: string;
  type: string;
}

function formWith(file: UploadFile): FormData {
  const form = new FormData();
  // React Native's FormData takes {uri, name, type} for a file on the phone.
  form.append("file", file as unknown as Blob);
  return form;
}

export const memberApi = {
  // Before signing in.
  gym: (slug: string) => request<PublicGym>(gymPath(slug, "/gym"), { auth: false }),
  requestCode: (slug: string, who: { phone?: string; email?: string }) =>
    request<CodeSent>(gymPath(slug, "/otp/request"), { body: who, auth: false }),
  verifyCode: (
    slug: string,
    body: { phone?: string; email?: string; code: string; member_id?: string },
  ) =>
    request<MemberSignIn>(gymPath(slug, "/otp/verify"), {
      body: { ...body, client: "app" },
      auth: false,
    }),
  /** The QR the desk showed (PLAN.md §18.4): signed in with no code. */
  deskSignIn: (slug: string, token: string) =>
    request<MemberSignIn>(gymPath(slug, "/desk-sign-in"), {
      body: { token, client: "app" },
      auth: false,
    }),
  joinOptions: (slug: string) =>
    request<JoinOptions>(gymPath(slug, "/join"), { auth: false }),
  askToJoin: (
    slug: string,
    body: {
      name: string;
      phone: string;
      plan_id?: string | null;
      source?: LeadSource;
      message?: string | null;
    },
    key: string,
  ) =>
    request<{ received: boolean }>(gymPath(slug, "/join"), {
      body,
      auth: false,
      idempotencyKey: key,
    }),
  logout: (refreshToken: string) =>
    request<void>("/api/v1/m/auth/logout", {
      body: { refresh_token: refreshToken },
      auth: false,
    }),

  // Signed in.
  me: () => request<MemberMe>("/api/v1/m/me"),
  updateMe: (body: { emergency_contact?: string | null; language?: Locale | null }) =>
    request<MemberMe>("/api/v1/m/me", { method: "PATCH", body }),
  uploadPhoto: (file: UploadFile) =>
    request<MemberMe>("/api/v1/m/me/photo", { form: formWith(file) }),
  changeEmail: (email: string) =>
    request<void>("/api/v1/m/me/email", { body: { email } }),
  confirmEmail: (email: string, code: string, key: string) =>
    request<MemberMe>("/api/v1/m/me/email/confirm", {
      body: { email, code },
      idempotencyKey: key,
    }),

  payments: () => request<MemberPayments>("/api/v1/m/me/payments"),
  receiptLink: (paymentId: string) =>
    request<ReceiptLink>(`/api/v1/m/me/payments/${paymentId}/receipt-link`, {
      method: "POST",
    }),
  visits: (month: string) => request<Visit[]>(`/api/v1/m/me/visits?month=${month}`),
  notices: () => request<Notice[]>("/api/v1/m/notices"),

  renewOptions: () => request<RenewOptions>("/api/v1/m/renew"),
  createRequest: (
    body: {
      plan_id: string;
      payment_method_id: string | null;
      amount: number;
      transaction_ref: string | null;
    },
    key: string,
  ) =>
    request<PaymentRequest>("/api/v1/m/payment-requests", {
      body,
      idempotencyKey: key,
    }),
  uploadScreenshot: (id: string, file: UploadFile) =>
    request<PaymentRequest>(`/api/v1/m/payment-requests/${id}/screenshot`, {
      form: formWith(file),
    }),
  withdraw: (id: string, key: string) =>
    request<PaymentRequest>(`/api/v1/m/payment-requests/${id}/withdraw`, {
      method: "POST",
      idempotencyKey: key,
    }),

  latestFreeze: () => request<FreezeRequest | null>("/api/v1/m/freeze-requests/latest"),
  askToFreeze: (
    body: { from_date: string; to_date: string; reason: string },
    key: string,
  ) =>
    request<FreezeRequest>("/api/v1/m/freeze-requests", { body, idempotencyKey: key }),
  withdrawFreeze: (id: string, key: string) =>
    request<FreezeRequest>(`/api/v1/m/freeze-requests/${id}/withdraw`, {
      method: "POST",
      idempotencyKey: key,
    }),

  pushStatus: (expoToken: string) =>
    request<PushStatus>(
      `/api/v1/m/me/push?expo_token=${encodeURIComponent(expoToken)}`,
    ),
  pushOn: (expoToken: string) =>
    request<PushStatus>("/api/v1/m/me/push", {
      body: { kind: "expo", expo_token: expoToken },
    }),
  pushOff: (expoToken: string) =>
    request<PushStatus>("/api/v1/m/me/push/off", { body: { expo_token: expoToken } }),
};
