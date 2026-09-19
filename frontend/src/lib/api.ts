/**
 * Talking to the GymBahi API.
 *
 * Requests go to /api/* on this origin; Next.js forwards them to FastAPI
 * (next.config.ts). The access token lives only in memory. The refresh token
 * is an httpOnly cookie the page cannot read, so a reload restores the session
 * by calling refresh(), and a 401 mid-session triggers one refresh and retry.
 */
import { isMessageKey, t } from "@/i18n";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: { field: string; type: string }[] = [],
    // Anything else the API sent with the error, e.g. `expected` or `owed`.
    readonly extra: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// --- types ------------------------------------------------------------------

export type PlanMonths = "ad" | "bs";
export type DateDisplay = "ad" | "bs" | "both";

export interface GymSettings {
  plan_months: PlanMonths;
  date_display: DateDisplay;
  dues_rule: "allow" | "warn" | "refuse";
  grace_days: number;
  rescan_minutes: number;
  reminder_language: "en" | "ne";
  member_code_prefix: string;
}

export interface Gym {
  id: string;
  slug: string;
  name: string;
  phone: string | null;
  address: string | null;
  logo_url: string | null;
  brand_color: string | null;
  status: string;
  settings: GymSettings;
}

export interface Staff {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  is_owner: boolean;
  is_platform_admin: boolean;
  last_login_at: string | null;
}

export interface Subscription {
  status: string;
  starts_on: string;
  ends_on: string;
  days_left: number;
}

export interface Me {
  staff: Staff;
  gym: Gym | null;
  permissions: string[];
  branch_ids: string[] | null;
  subscription: Subscription | null;
}

export interface Session {
  access_token: string;
  token_type: string;
  expires_in: number;
  me: Me;
}

export interface GymSignup {
  gym_name: string;
  slug: string;
  branch_name: string;
  plan_months: PlanMonths;
  date_display: DateDisplay;
  owner_name: string;
  owner_phone: string;
  owner_email: string;
  password: string;
}

// --- clients -------------------------------------------------------------------

/**
 * One signed-in audience: staff, a member, or a kiosk. Each keeps its own
 * access token in memory and knows how to refresh it (or, for a kiosk, sends
 * its device token instead).
 */
export function createClient<S extends { access_token: string | null }>(options: {
  refreshPath?: string;
  headers?: () => Record<string, string>;
}) {
  let accessToken: string | null = null;
  let onSessionLost: (() => void) | null = null;
  let refreshing: Promise<S | null> | null = null;

  function refreshSession(): Promise<S | null> {
    // Concurrent callers share one request: the server rotates the cookie on
    // every refresh, and two overlapping refreshes would race each other.
    refreshing ??= (async () => {
      if (!options.refreshPath) return null;
      try {
        const response = await fetch(options.refreshPath, {
          method: "POST",
          credentials: "same-origin",
        });
        if (!response.ok) {
          accessToken = null;
          return null;
        }
        const session = (await response.json()) as S;
        accessToken = session.access_token;
        return session;
      } catch {
        return null;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  async function request<T>(
    path: string,
    init: RequestInit = {},
    retried = false,
  ): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    for (const [key, value] of Object.entries(options.headers?.() ?? {})) {
      headers.set(key, value);
    }

    let response: Response;
    try {
      response = await fetch(path, { ...init, headers, credentials: "same-origin" });
    } catch {
      throw new ApiError(0, "network", t("errors.network"));
    }

    if (response.status === 401 && accessToken && !retried) {
      // Most likely the 15-minute access token ran out: refresh once and retry.
      if (await refreshSession()) return request<T>(path, init, true);
      onSessionLost?.();
    }
    if (!response.ok) throw await toError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    request,
    refreshSession,
    setAccessToken: (token: string | null) => {
      accessToken = token;
    },
    /** Called when the session is gone for good, so the app can show sign-in. */
    setSessionLostHandler: (handler: (() => void) | null) => {
      onSessionLost = handler;
    },
  };
}

async function toError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const { code, detail, fields, ...extra } = body ?? {};
  return new ApiError(
    response.status,
    code ?? "http_" + response.status,
    typeof detail === "string" ? detail : response.statusText,
    Array.isArray(fields) ? fields : [],
    extra,
  );
}

const staff = createClient<Session>({ refreshPath: "/api/v1/auth/refresh" });
export const request = staff.request;
export const refreshSession = staff.refreshSession;
export const setAccessToken = staff.setAccessToken;
export const setSessionLostHandler = staff.setSessionLostHandler;

/** A message for the person at the screen, in their language. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "validation_error" && error.fields.length > 0) {
      const names = error.fields.map(({ field }) => {
        const key = `field.${field}`;
        return isMessageKey(key) ? t(key) : field;
      });
      return t("errors.validation_error", { fields: [...new Set(names)].join(", ") });
    }
    if (error.code === "validation_error") return t("errors.validation_error_form");
    const key = `errors.${error.code}`;
    if (isMessageKey(key)) return t(key);
    return error.message || t("errors.generic");
  }
  return t("errors.generic");
}

// --- endpoints --------------------------------------------------------------

const json = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

export const authApi = {
  registerGym: (payload: GymSignup) =>
    request<Session>("/api/v1/auth/register-gym", json(payload)),
  login: (identifier: string, password: string) =>
    request<Session>("/api/v1/auth/login", json({ identifier, password })),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<Me>("/api/v1/auth/me"),
};

// --- M1: members and money ----------------------------------------------------

export type Method = "cash" | "esewa" | "khalti" | "fonepay" | "bank";
export type AccountKind = "esewa" | "khalti" | "fonepay" | "bank" | "other";
export type MemberStatus = "active" | "frozen" | "upcoming" | "expired" | "none";
export type MembershipStatus =
  "active" | "frozen" | "upcoming" | "expired" | "cancelled";

export interface Branch {
  id: string;
  name: string;
  address: string | null;
  phone: string | null;
  is_active: boolean;
}

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

export interface PaymentListItem extends Payment {
  member_name: string;
  member_code: string;
}

export interface Freeze {
  id: string;
  from_date: string;
  to_date: string;
  reason: string | null;
}

export interface Membership {
  id: string;
  member_id: string;
  plan_id: string | null;
  plan_name: string;
  branch_id: string;
  start_date: string;
  end_date: string;
  price: number;
  discount: number;
  admission_fee: number;
  cancelled_at: string | null;
  cancel_reason: string | null;
  source: string;
  created_at: string;
  status: MembershipStatus;
  days_left: number;
  total: number;
  paid: number;
  dues: number;
  freezes: Freeze[];
}

export interface Member {
  id: string;
  member_code: string;
  name: string;
  phone: string;
  email: string | null;
  gender: "male" | "female" | "other" | null;
  date_of_birth: string | null;
  address: string | null;
  emergency_contact: string | null;
  notes: string | null;
  home_branch_id: string;
  joined_on: string;
  app_access: boolean;
  is_archived: boolean;
  created_at: string;
  photo_url: string | null;
  status: MemberStatus;
  current: {
    id: string;
    plan_name: string;
    start_date: string;
    end_date: string;
  } | null;
  valid_until: string | null;
  days_left: number;
  dues: number;
}

export interface MemberDetail extends Member {
  memberships: Membership[];
  payments: Payment[];
  renewal_starts_on: string;
  first_membership: boolean;
}

export interface PhoneMatch {
  id: string;
  name: string;
  member_code: string;
}

export interface PaymentInput {
  amount: number;
  method: Method;
  transaction_ref?: string | null;
  paid_at?: string | null;
  note?: string | null;
}

export interface SaleInput {
  plan_id: string;
  branch_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  price?: number | null;
  discount?: number;
  admission_fee?: number | null;
  payment?: PaymentInput | null;
}

export interface MemberInput {
  name: string;
  phone: string;
  email?: string | null;
  gender?: Member["gender"];
  date_of_birth?: string | null;
  address?: string | null;
  emergency_contact?: string | null;
  notes?: string | null;
  home_branch_id?: string | null;
}

export interface HistoryEntry {
  id: string;
  at: string;
  action: string;
  actor_name: string | null;
  changes: Record<string, unknown> | null;
  reason: string | null;
}

export interface Receipt {
  payment: Payment;
  gym_name: string;
  gym_phone: string | null;
  gym_address: string | null;
  branch_name: string | null;
  member_name: string;
  member_code: string;
  member_phone: string;
  plan_name: string | null;
  start_date: string | null;
  end_date: string | null;
  membership_total: number | null;
  dues_after: number | null;
  date_display: DateDisplay;
}

export interface StaffMember {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  is_owner: boolean;
  is_active: boolean;
  permissions: string[];
  branch_ids: string[];
  last_login_at: string | null;
  created_at: string;
}

export interface PermissionCatalog {
  permissions: { key: string; area: string }[];
  presets: Record<string, string[]>;
  grantable: string[];
}

export interface MemberFilters {
  q?: string;
  status?: MemberStatus | "";
  branch_id?: string;
  has_dues?: boolean;
  expiring_within?: number;
  archived?: boolean;
  sort?: "name" | "code" | "recent";
  limit?: number;
  offset?: number;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "")
      search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

function upload<T>(path: string, file: Blob, name = "image.jpg"): Promise<T> {
  const form = new FormData();
  form.append("file", file, name);
  return request<T>(path, { method: "POST", body: form });
}

export const gymApi = {
  get: () => request<Gym>("/api/v1/gym"),
  update: (patch: Record<string, unknown>) =>
    request<Gym>("/api/v1/gym", send("PATCH", patch)),
  updateCheckInRules: (patch: Partial<GymSettings>) =>
    request<Gym>("/api/v1/gym/check-in-rules", send("PATCH", patch)),
  uploadLogo: (file: Blob) => upload<Gym>("/api/v1/gym/logo", file),
  changePassword: (current_password: string, new_password: string) =>
    request<void>(
      "/api/v1/auth/password",
      send("POST", { current_password, new_password }),
    ),
};

export const branchesApi = {
  list: () => request<Branch[]>("/api/v1/branches"),
  create: (body: Partial<Branch>) =>
    request<Branch>("/api/v1/branches", send("POST", body)),
  update: (id: string, body: Partial<Branch>) =>
    request<Branch>(`/api/v1/branches/${id}`, send("PATCH", body)),
};

export const plansApi = {
  list: (includeHidden = false) =>
    request<Plan[]>(`/api/v1/plans${includeHidden ? "?include_hidden=true" : ""}`),
  create: (body: Partial<Plan>) => request<Plan>("/api/v1/plans", send("POST", body)),
  update: (id: string, body: Partial<Plan>) =>
    request<Plan>(`/api/v1/plans/${id}`, send("PATCH", body)),
};

export const paymentMethodsApi = {
  list: (includeHidden = false) =>
    request<PaymentMethodAccount[]>(
      `/api/v1/payment-methods${includeHidden ? "?include_hidden=true" : ""}`,
    ),
  create: (body: Partial<PaymentMethodAccount>) =>
    request<PaymentMethodAccount>("/api/v1/payment-methods", send("POST", body)),
  update: (id: string, body: Partial<PaymentMethodAccount>) =>
    request<PaymentMethodAccount>(`/api/v1/payment-methods/${id}`, send("PATCH", body)),
  uploadQr: (id: string, file: Blob) =>
    upload<PaymentMethodAccount>(`/api/v1/payment-methods/${id}/qr`, file),
};

export const membersApi = {
  list: (filters: MemberFilters = {}) =>
    request<{ items: Member[]; total: number }>(`/api/v1/members${query(filters)}`),
  get: (id: string) => request<MemberDetail>(`/api/v1/members/${id}`),
  phoneCheck: (phone: string) =>
    request<PhoneMatch[]>(`/api/v1/members/phone-check${query({ phone })}`),
  create: (body: MemberInput & { membership?: SaleInput | null }) =>
    request<{
      member: MemberDetail;
      payment_id: string | null;
      same_phone: PhoneMatch[];
    }>("/api/v1/members", send("POST", body)),
  update: (id: string, body: Partial<MemberInput>) =>
    request<MemberDetail>(`/api/v1/members/${id}`, send("PATCH", body)),
  archive: (id: string, reason?: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/archive`, send("POST", { reason })),
  unarchive: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/unarchive`, send("POST")),
  uploadPhoto: (id: string, file: Blob) =>
    upload<MemberDetail>(`/api/v1/members/${id}/photo`, file),
  sell: (id: string, body: SaleInput) =>
    request<{ membership: Membership; payment: Payment | null }>(
      `/api/v1/members/${id}/memberships`,
      send("POST", body),
    ),
  history: (id: string) => request<HistoryEntry[]>(`/api/v1/members/${id}/history`),
};

export const membershipsApi = {
  get: (id: string) => request<Membership>(`/api/v1/memberships/${id}`),
  update: (id: string, body: Partial<SaleInput> & { reason?: string }) =>
    request<Membership>(`/api/v1/memberships/${id}`, send("PATCH", body)),
  extend: (id: string, days: number, reason: string) =>
    request<Membership>(
      `/api/v1/memberships/${id}/extend`,
      send("POST", { days, reason }),
    ),
  extendAll: (days: number, reason: string, branch_id?: string | null) =>
    request<{ extended: number }>(
      "/api/v1/memberships/extend-all",
      send("POST", { days, reason, branch_id: branch_id || null }),
    ),
  freeze: (id: string, from_date: string, to_date: string, reason?: string) =>
    request<Membership>(
      `/api/v1/memberships/${id}/freeze`,
      send("POST", { from_date, to_date, reason: reason || null }),
    ),
  endFreeze: (id: string, freezeId: string) =>
    request<Membership>(
      `/api/v1/memberships/${id}/freezes/${freezeId}/end`,
      send("POST"),
    ),
  cancel: (id: string, reason: string, refund?: PaymentInput | null) =>
    request<{ membership: Membership; payment: Payment | null }>(
      `/api/v1/memberships/${id}/cancel`,
      send("POST", { reason, refund: refund ?? null }),
    ),
  remove: (id: string) => request<void>(`/api/v1/memberships/${id}`, send("DELETE")),
  history: (id: string) => request<HistoryEntry[]>(`/api/v1/memberships/${id}/history`),
};

export const paymentsApi = {
  collect: (membership_id: string, payment: PaymentInput) =>
    request<Payment>("/api/v1/payments", send("POST", { membership_id, ...payment })),
  refund: (membership_id: string, payment: PaymentInput) =>
    request<Payment>(
      "/api/v1/payments/refunds",
      send("POST", { membership_id, ...payment }),
    ),
  list: (filters: {
    date_from?: string;
    date_to?: string;
    method?: string;
    limit?: number;
    offset?: number;
  }) =>
    request<{
      items: PaymentListItem[];
      total: number;
      sum_amount: number;
      by_method: Record<string, number>;
    }>(`/api/v1/payments${query(filters)}`),
  update: (id: string, body: Partial<PaymentInput> & { reason?: string }) =>
    request<Payment>(`/api/v1/payments/${id}`, send("PATCH", body)),
  void: (id: string, reason: string) =>
    request<Payment>(`/api/v1/payments/${id}/void`, send("POST", { reason })),
  receipt: (id: string) => request<Receipt>(`/api/v1/payments/${id}/receipt`),
};

export const staffApi = {
  list: () => request<StaffMember[]>("/api/v1/staff"),
  catalog: () => request<PermissionCatalog>("/api/v1/staff/permissions"),
  create: (body: Record<string, unknown>) =>
    request<StaffMember>("/api/v1/staff", send("POST", body)),
  update: (id: string, body: Record<string, unknown>) =>
    request<StaffMember>(`/api/v1/staff/${id}`, send("PATCH", body)),
  setPassword: (id: string, new_password: string) =>
    request<void>(`/api/v1/staff/${id}/password`, send("POST", { new_password })),
};

// --- M2: expiry, SMS, reminders, notices ---------------------------------------

export interface SmsMessage {
  id: string;
  member_id: string | null;
  to: string;
  body: string;
  kind: string;
  status: "queued" | "sent" | "failed" | "no_credit";
  segments: number;
  error: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface ReminderRule {
  id: string;
  days_from_expiry: number;
  template: string;
  enabled: boolean;
}

export interface Notice {
  id: string;
  branch_id: string | null;
  title: string;
  body: string;
  published_at: string;
  send_sms: boolean;
  sms_count: number;
}

export interface NoticeInput {
  title: string;
  body: string;
  branch_id?: string | null;
  send_sms: boolean;
}

export const messagesApi = {
  expiring: () =>
    request<{ due_today: Member[]; due_this_week: Member[]; lapsed: Member[] }>(
      "/api/v1/lists/expiring",
    ),
  smsLog: (memberId?: string) =>
    request<{ balance: number; items: SmsMessage[] }>(
      `/api/v1/sms${query({ member_id: memberId })}`,
    ),
  smsMember: (memberId: string, body: { reminder?: boolean; body?: string }) =>
    request<SmsMessage>(`/api/v1/members/${memberId}/sms`, send("POST", body)),
  rules: () => request<ReminderRule[]>("/api/v1/reminder-rules"),
  createRule: (body: Omit<ReminderRule, "id">) =>
    request<ReminderRule>("/api/v1/reminder-rules", send("POST", body)),
  updateRule: (id: string, body: Partial<ReminderRule>) =>
    request<ReminderRule>(`/api/v1/reminder-rules/${id}`, send("PATCH", body)),
  deleteRule: (id: string) =>
    request<void>(`/api/v1/reminder-rules/${id}`, send("DELETE")),
  templates: () =>
    request<{ welcome_sms: string; membership_sms: string }>("/api/v1/sms-templates"),
  updateTemplates: (body: { welcome_sms?: string; membership_sms?: string }) =>
    request<{ welcome_sms: string; membership_sms: string }>(
      "/api/v1/sms-templates",
      send("PATCH", body),
    ),
  notices: () => request<Notice[]>("/api/v1/notices"),
  noticeCost: (body: NoticeInput) =>
    request<{
      recipients: number;
      segments_each: number;
      total_credits: number;
      balance: number;
    }>("/api/v1/notices/cost", send("POST", body)),
  publishNotice: (body: NoticeInput) =>
    request<Notice>("/api/v1/notices", send("POST", body)),
  deleteNotice: (id: string) => request<void>(`/api/v1/notices/${id}`, send("DELETE")),
};

// --- M3: door, devices, app payments, member access ---------------------------

export interface ScanResult {
  result: string;
  let_in: boolean;
  reason: string | null;
  check_in_id: string | null;
  member_id: string | null;
  member_name: string | null;
  member_code: string | null;
  photo_url: string | null;
  plan_name: string | null;
  days_left: number;
  valid_until: string | null;
  dues: number;
  can_override: boolean;
}

export interface Device {
  id: string;
  branch_id: string;
  name: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface CheckInRow {
  id: string;
  at: string;
  member_id: string;
  member_name: string;
  member_code: string;
  branch_id: string;
  method: string;
  result: string;
  staff_name: string | null;
  note: string | null;
}

export interface CardInfo {
  member_id: string;
  member_code: string;
  name: string;
  photo_url: string | null;
  card_code: string;
  gym_name: string;
  logo_url: string | null;
}

export const doorApi = {
  devices: () => request<Device[]>("/api/v1/devices"),
  registerDevice: (branch_id: string, name: string) =>
    request<{ device: Device; token: string }>(
      "/api/v1/devices",
      send("POST", { branch_id, name }),
    ),
  revokeDevice: (id: string) =>
    request<Device>(`/api/v1/devices/${id}/revoke`, send("POST")),
  scan: (code: string, branch_id: string) =>
    request<ScanResult>("/api/v1/check-ins/scan", send("POST", { code, branch_id })),
  manual: (body: {
    member_id: string;
    branch_id: string;
    override?: boolean;
    note?: string;
  }) => request<ScanResult>("/api/v1/check-ins/manual", send("POST", body)),
  checkIns: (filters: {
    date_from?: string;
    date_to?: string;
    member_id?: string;
    denied_only?: boolean;
    limit?: number;
  }) =>
    request<{ items: CheckInRow[]; total: number }>(
      `/api/v1/check-ins${query(filters)}`,
    ),
  summary: (date_from: string, date_to: string) =>
    request<{
      by_day: Record<string, number>;
      by_hour: Record<string, number>;
      denied: number;
      let_in: number;
      unique_members: number;
    }>(`/api/v1/check-ins/summary${query({ date_from, date_to })}`),
};

export const paymentRequestsApi = {
  list: (status = "pending") =>
    request<import("./memberApi").PaymentRequest[]>(
      `/api/v1/payment-requests?status=${status}`,
    ),
  count: () => request<{ pending: number }>("/api/v1/payment-requests/count"),
  approve: (
    id: string,
    body: { price?: number | null; discount?: number; accept_part_payment?: boolean },
  ) =>
    request<import("./memberApi").PaymentRequest>(
      `/api/v1/payment-requests/${id}/approve`,
      send("POST", body),
    ),
  reject: (id: string, reason: string) =>
    request<import("./memberApi").PaymentRequest>(
      `/api/v1/payment-requests/${id}/reject`,
      send("POST", { reason }),
    ),
};

export const accessApi = {
  setAccess: (id: string, app_access: boolean) =>
    request<MemberDetail>(
      `/api/v1/members/${id}/access`,
      send("PATCH", { app_access }),
    ),
  signOutAll: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/sign-out-all`, send("POST")),
  resendWelcome: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/resend-welcome`, send("POST")),
  reissueQr: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/qr/reissue`, send("POST")),
  card: (id: string) => request<CardInfo>(`/api/v1/members/${id}/card`),
  reissueCard: (id: string) =>
    request<CardInfo>(`/api/v1/members/${id}/card/reissue`, send("POST")),
};
