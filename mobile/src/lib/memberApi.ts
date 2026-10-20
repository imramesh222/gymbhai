/** The member app's API (PLAN.md §8 "Member app", §17), as the phone calls it. */
import * as Linking from "expo-linking";

import type { Locale } from "@shared/i18n";
import type {
  AppClasses,
  Progress,
  ProgressInput,
  CodeSent,
  FreezeRequest,
  JoinOptions,
  LeadSource,
  MemberDevice,
  MemberMe,
  MemberPayments,
  MemberSignIn,
  Notice,
  OnlinePayment,
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
  /** Where they're signed in (§17.5). */
  devices: () => request<MemberDevice[]>("/api/v1/m/me/sessions"),
  signOutDevice: (id: string) =>
    request<void>(`/api/v1/m/me/sessions/${id}/sign-out`, { method: "POST" }),
  signOutOtherDevices: () =>
    request<{ signed_out: number }>("/api/v1/m/me/sessions/sign-out-others", {
      method: "POST",
    }),
  updateMe: (body: {
    emergency_contact?: string | null;
    language?: Locale | null;
    whatsapp_agreed?: boolean;
  }) => request<MemberMe>("/api/v1/m/me", { method: "PATCH", body }),
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
  /** Their own progress (§19.5): checks, height, and their private photos. */
  progress: () => request<Progress>("/api/v1/m/progress"),
  recordProgress: (body: ProgressInput, key: string) =>
    request<Progress>("/api/v1/m/progress", { body, idempotencyKey: key }),
  deleteProgress: (id: string, key: string) =>
    request<Progress>(`/api/v1/m/progress/${id}`, {
      method: "DELETE",
      idempotencyKey: key,
    }),
  setHeight: (height_mm: number | null, key: string) =>
    request<Progress>("/api/v1/m/progress/height", {
      method: "PUT",
      body: { height_mm },
      idempotencyKey: key,
    }),
  addProgressPhoto: (file: UploadFile, pose: string, key: string) => {
    const form = formWith(file);
    form.append("pose", pose);
    return request<Progress>("/api/v1/m/progress/photos", {
      form,
      idempotencyKey: key,
    });
  },
  shareProgressPhoto: (id: string, shared: boolean, key: string) =>
    request<Progress>(`/api/v1/m/progress/photos/${id}`, {
      method: "PATCH",
      body: { shared },
      idempotencyKey: key,
    }),
  deleteProgressPhoto: (id: string, key: string) =>
    request<Progress>(`/api/v1/m/progress/photos/${id}`, {
      method: "DELETE",
      idempotencyKey: key,
    }),
  /** A week of classes at their branch (§19.4). */
  classes: (from: string) => request<AppClasses>(`/api/v1/m/classes?from=${from}`),
  bookClass: (classId: string, key: string) =>
    request<AppClasses>(`/api/v1/m/classes/${classId}/book`, {
      method: "POST",
      idempotencyKey: key,
    }),
  cancelClassBooking: (bookingId: string, key: string) =>
    request<AppClasses>(`/api/v1/m/class-bookings/${bookingId}/cancel`, {
      method: "POST",
      idempotencyKey: key,
    }),
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
  /** Pay through the gym's merchant account (§20.2): the wallet's page opens
   * in the phone's browser and comes back to the app. */
  startOnlinePayment: (body: { plan_id: string; payment_method_id: string }) =>
    request<OnlinePayment>("/api/v1/m/online-payments", {
      // Back to this app's Renew: gymbhai://, a gym's own app's scheme, or
      // Expo Go's exp:// while developing.
      body: { ...body, from_app: true, return_to: Linking.createURL("renew") },
    }),
  /** Ask the wallet now whether it's paid (§20.2): back from its page. */
  checkOnlinePayment: (id: string) =>
    request<OnlinePayment>(`/api/v1/m/online-payments/${id}/check`, {
      method: "POST",
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
