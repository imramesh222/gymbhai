/**
 * Talking to the GymBhai API.
 *
 * Requests go to /api/* on this origin; Next.js forwards them to FastAPI
 * (next.config.ts). The access token lives only in memory. The refresh token
 * is an httpOnly cookie the page cannot read, so a reload restores the session
 * by calling refresh(), and a 401 mid-session triggers one refresh and retry.
 */
import type { Digits, Locale } from "@/i18n";
import { isMessageKey, t } from "@/i18n";
import type {
  AccessWindow,
  FreezeRequest,
  Method,
  Notice,
  Payment,
  PaymentMethodAccount,
  Plan,
  ReceiptLink,
} from "@shared/types";

// The member-facing types live in shared/ (PLAN.md §17): one copy for the
// web app and the phone app.
export type {
  AccountKind,
  FreezeRequest,
  Method,
  Notice,
  Payment,
  PaymentMethodAccount,
  Plan,
} from "@shared/types";

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
  not_visiting_days: number;
  language: Locale;
  digits: Digits;
  member_code_prefix: string;
  daily_summary_sms: boolean;
  show_busyness: boolean;
  join_form: boolean;
  require_two_step: boolean;
  poster_printed: boolean;
  setup_dismissed: boolean;
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
  two_step_enabled: boolean;
}

export interface Subscription {
  status: string;
  plan_name: string | null;
  starts_on: string | null;
  ends_on: string | null;
  days_left: number;
  phase: "ok" | "ending" | "grace" | "read_only";
  grace_ends_on: string | null;
  over_limit: boolean;
}

export interface Me {
  staff: Staff;
  gym: Gym | null;
  /** Must use two-step sign-in; until it's on, only setting it up works. */
  two_step_required: boolean;
  permissions: string[];
  branch_ids: string[] | null;
  subscription: Subscription | null;
  /** Help: our WhatsApp/Viber number, if set (§16.5, 10.3). */
  support_whatsapp: string | null;
  /** What's new has something they haven't opened (10.4). */
  changelog_unread: boolean;
  /** The language to show: their own choice, else the gym's (§16.6). */
  language: Locale;
  own_language: Locale | null;
  digits: Digits;
}

export interface Session {
  access_token: string;
  token_type: string;
  expires_in: number;
  me: Me;
}

/** The password was right; the code from the authenticator app comes next. */
export interface TwoStepChallenge {
  two_step_token: string;
  expires_in: number;
}

/** A device signed in to your account (My account → Devices). */
export interface DeviceSession {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string | null;
  current: boolean;
}

export interface TwoStepStatus {
  enabled: boolean;
  required: boolean;
  recovery_codes_left: number;
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
  accept_terms: boolean;
  /** The gym that sent them (§16.5, 10.5). */
  ref?: string | null;
  /** The gym's language (§16.6). */
  language?: Locale;
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

  /**
   * A new access token from the refresh cookie. Null means the session is
   * over (the server said 401). Anything else — no signal, a timeout, a
   * server error — throws ApiError "network": a flaky gym Wi-Fi must never
   * sign the desk out.
   */
  function refreshSession(): Promise<S | null> {
    // Concurrent callers share one request: the server rotates the cookie on
    // every refresh, and two overlapping refreshes would race each other.
    refreshing ??= (async () => {
      if (!options.refreshPath) return null;
      try {
        let response: Response;
        try {
          response = await fetch(options.refreshPath, {
            method: "POST",
            credentials: "same-origin",
            // The server rotates the cookie on every refresh. If the page
            // navigates away mid-request, keepalive still lets the new cookie
            // land; otherwise the browser keeps a token that dies 30 seconds
            // later and the next page load signs the person out.
            keepalive: true,
          });
        } catch {
          throw new ApiError(0, "network", t("errors.network"));
        }
        if (response.status === 401 || response.status === 403) {
          accessToken = null;
          return null;
        }
        if (!response.ok)
          throw new ApiError(response.status, "network", t("errors.network"));
        const session = (await response.json()) as S;
        accessToken = session.access_token;
        return session;
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

  /**
   * An open event stream (lib/live.ts), signed in like `request`: a 401
   * refreshes the access token once and tries again.
   */
  async function open(path: string, signal: AbortSignal): Promise<Response> {
    const send = () =>
      fetch(path, {
        headers: {
          Accept: "text/event-stream",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        credentials: "same-origin",
        cache: "no-store",
        signal,
      });
    let response = await send();
    if (response.status === 401 && accessToken) {
      if (await refreshSession()) response = await send();
      else onSessionLost?.();
    }
    if (!response.ok || !response.body) throw await toError(response);
    return response;
  }

  return {
    request,
    refreshSession,
    open,
    authHeader: (): Record<string, string> =>
      accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
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
/** The dashboard's live updates (backend/app/services/live.py). */
export const openStaffLive = (signal: AbortSignal) =>
  staff.open("/api/v1/live", signal);
const staffAuthHeader = staff.authHeader;

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

export const languageApi = {
  /** Null follows the gym's language (§16.6). */
  set: (language: Locale | null) =>
    request<Me>("/api/v1/auth/me/language", send("PUT", { language })),
};

export const authApi = {
  registerGym: (payload: GymSignup) =>
    request<Session>("/api/v1/auth/register-gym", json(payload)),
  login: (identifier: string, password: string) =>
    request<Session | TwoStepChallenge>(
      "/api/v1/auth/login",
      json({ identifier, password }),
    ),
  loginTwoStep: (two_step_token: string, code: string) =>
    request<Session>("/api/v1/auth/login/two-step", json({ two_step_token, code })),
  sessions: () => request<DeviceSession[]>("/api/v1/auth/sessions"),
  signOutDevice: (id: string) =>
    request<void>(`/api/v1/auth/sessions/${id}/sign-out`, { method: "POST" }),
  signOutOthers: () =>
    request<{ signed_out: number }>("/api/v1/auth/sessions/sign-out-others", {
      method: "POST",
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<Me>("/api/v1/auth/me"),
  requestPasswordReset: (identifier: string) =>
    request<{ expires_in: number }>(
      "/api/v1/auth/password-reset",
      json({ identifier }),
    ),
  confirmPasswordReset: (identifier: string, code: string, new_password: string) =>
    request<void>(
      "/api/v1/auth/password-reset/confirm",
      json({ identifier, code, new_password }),
    ),
};

/** Your own two-step sign-in (PLAN.md §16.1). */
export const twoStepApi = {
  status: () => request<TwoStepStatus>("/api/v1/auth/two-step"),
  setup: (password: string) =>
    request<{ secret: string; uri: string }>(
      "/api/v1/auth/two-step/setup",
      json({ password }),
    ),
  enable: (code: string) =>
    request<{ recovery_codes: string[] }>(
      "/api/v1/auth/two-step/enable",
      json({ code }),
    ),
  newRecoveryCodes: (password: string) =>
    request<{ recovery_codes: string[] }>(
      "/api/v1/auth/two-step/recovery-codes",
      json({ password }),
    ),
  disable: (password: string) =>
    request<void>("/api/v1/auth/two-step/disable", json({ password })),
};

// --- M1: members and money ----------------------------------------------------

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
  visit_limit: number | null;
  visits_used: number | null;
  access_hours: AccessWindow[] | null;
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
  /** Erased at their request: no personal details left (PLAN.md §16.1). */
  erased_at: string | null;
  created_at: string;
  photo_url: string | null;
  status: MemberStatus;
  current: {
    id: string;
    plan_name: string;
    start_date: string;
    end_date: string;
    visit_limit: number | null;
    visits_left: number | null;
    access_hours: AccessWindow[] | null;
  } | null;
  valid_until: string | null;
  days_left: number;
  dues: number;
  /** Lists only: the last time they were let in. */
  last_visit_at?: string | null;
}

export interface MemberCounts {
  all: number;
  active: number;
  expiring: number;
  expired: number;
  dues: number;
  frozen: number;
  not_visiting: number;
  archived: number;
}

export interface MemberDetail extends Member {
  referred_by_id: string | null;
  referred_by_name: string | null;
  memberships: Membership[];
  payments: Payment[];
  renewal_starts_on: string;
  first_membership: boolean;
  /** Their number on the gym's fingerprint and face readers, if it has any. */
  reader_pin: string | null;
  /** Their newest app sign-in, still signed in or not. */
  app_signed_in_at: string | null;
}

/** The QR for signing in at the desk (PLAN.md §18.4). */
export interface SignInLink {
  url: string;
  made_at: string;
  expires_at: string;
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
  /** The member who sent them (§16.4, 9.6). */
  referred_by_id?: string | null;
  /** Convert: the enquiry they came from (9.1). */
  lead_id?: string | null;
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
  /** For personal training (§18.3): the dates are its, not a membership's. */
  training: boolean;
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
  two_step_enabled: boolean;
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
  not_visiting?: boolean;
  archived?: boolean;
  sort?: "name" | "code" | "recent" | "dues" | "last_visit";
  direction?: "asc" | "desc";
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

/** A money request the API may receive twice; see lib/idempotency.ts. */
const once = (init: RequestInit, key?: string): RequestInit =>
  key ? { ...init, headers: { ...init.headers, "Idempotency-Key": key } } : init;

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
  updateSecurity: (require_two_step: boolean) =>
    request<Gym>("/api/v1/gym/security", send("PATCH", { require_two_step })),
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
  counts: () => request<MemberCounts>("/api/v1/members/counts"),
  smsMany: (member_ids: string[], body: string) =>
    request<{ queued: number }>(
      "/api/v1/members/sms",
      send("POST", { member_ids, body }),
    ),
  get: (id: string) => request<MemberDetail>(`/api/v1/members/${id}`),
  phoneCheck: (phone: string) =>
    request<PhoneMatch[]>(`/api/v1/members/phone-check${query({ phone })}`),
  create: (body: MemberInput & { membership?: SaleInput | null }, key?: string) =>
    request<{
      member: MemberDetail;
      payment_id: string | null;
      same_phone: PhoneMatch[];
    }>("/api/v1/members", once(send("POST", body), key)),
  update: (id: string, body: Partial<MemberInput>) =>
    request<MemberDetail>(`/api/v1/members/${id}`, send("PATCH", body)),
  archive: (id: string, reason?: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/archive`, send("POST", { reason })),
  unarchive: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/unarchive`, send("POST")),
  erase: (id: string) =>
    request<MemberDetail>(`/api/v1/members/${id}/erase`, send("POST")),
  uploadPhoto: (id: string, file: Blob) =>
    upload<MemberDetail>(`/api/v1/members/${id}/photo`, file),
  sell: (id: string, body: SaleInput, key?: string) =>
    request<{ membership: Membership; payment: Payment | null }>(
      `/api/v1/members/${id}/memberships`,
      once(send("POST", body), key),
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
  collect: (membership_id: string, payment: PaymentInput, key?: string) =>
    request<Payment>(
      "/api/v1/payments",
      once(send("POST", { membership_id, ...payment }), key),
    ),
  refund: (membership_id: string, payment: PaymentInput, key?: string) =>
    request<Payment>(
      "/api/v1/payments/refunds",
      once(send("POST", { membership_id, ...payment }), key),
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
  receiptLink: (id: string) =>
    request<ReceiptLink>(`/api/v1/payments/${id}/receipt-link`, send("POST")),
};

/** Money the gym spent: rent, salaries, bills (PLAN.md §18.1). */
export const EXPENSE_CATEGORIES = [
  "rent",
  "salaries",
  "electricity",
  "water",
  "internet",
  "equipment",
  "repairs",
  "cleaning",
  "marketing",
  "fees",
  "other",
] as const;
export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export interface Expense {
  id: string;
  /** Null: the whole gym's, not one branch's. */
  branch_id: string | null;
  category: ExpenseCategory;
  amount: number;
  spent_on: string;
  method: Method;
  paid_to: string | null;
  note: string | null;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
}

export interface ExpenseInput {
  category: ExpenseCategory;
  amount: number;
  spent_on: string;
  method: Method;
  paid_to: string | null;
  note: string | null;
  branch_id: string | null;
}

export interface ExpenseList {
  /** A month of the gym's own calendar, "2083-06" (BS) or "2026-10" (AD). */
  month: string;
  calendar: "ad" | "bs";
  first_day: string;
  last_day: string;
  items: Expense[];
  /** Voided ones left out. */
  sum_amount: number;
  by_category: Partial<Record<ExpenseCategory, number>>;
}

export const expensesApi = {
  list: (filters: { month?: string; category?: ExpenseCategory } = {}) =>
    request<ExpenseList>(`/api/v1/expenses${query(filters)}`),
  create: (body: ExpenseInput, key?: string) =>
    request<Expense>("/api/v1/expenses", once(send("POST", body), key)),
  update: (id: string, body: Partial<ExpenseInput> & { reason?: string | null }) =>
    request<Expense>(`/api/v1/expenses/${id}`, send("PATCH", body)),
  void: (id: string, reason: string) =>
    request<Expense>(`/api/v1/expenses/${id}/void`, send("POST", { reason })),
};

// --- personal training (PLAN.md §18.3) ---

export type PtKind = "monthly" | "sessions";
export type PtStatus = "active" | "upcoming" | "used_up" | "ended" | "cancelled";

export interface PtPlan {
  id: string;
  name: string;
  kind: PtKind;
  /** A pack's size; null for monthly training. */
  sessions: number | null;
  duration_months: number | null;
  duration_days: number | null;
  price: number;
  is_active: boolean;
  sort_order: number;
}

export type PtPlanInput = Omit<PtPlan, "id" | "is_active" | "sort_order"> & {
  is_active?: boolean;
};

export interface Trainer {
  id: string;
  name: string;
}

export interface PtSession {
  id: string;
  package_id: string;
  trained_on: string;
  trainer_id: string;
  trainer_name: string | null;
  recorded_by_name: string | null;
  note: string | null;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
}

export interface PtPackage {
  id: string;
  member_id: string;
  member_name: string;
  member_code: string;
  plan_id: string | null;
  plan_name: string;
  kind: PtKind;
  sessions: number | null;
  trainer_id: string;
  trainer_name: string | null;
  branch_id: string;
  start_date: string;
  end_date: string;
  price: number;
  discount: number;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  status: PtStatus;
  sessions_used: number;
  sessions_left: number | null;
  days_left: number;
  last_session_on: string | null;
  total: number;
  paid: number;
  dues: number;
}

/** On the member's profile: every session, voided too, and the money. */
export interface PtPackageDetail extends PtPackage {
  session_log: PtSession[];
  payments: Payment[];
}

export interface PtSaleInput {
  plan_id: string;
  trainer_id: string;
  branch_id?: string | null;
  start_date: string;
  end_date: string;
  price: number | null;
  discount: number;
  payment: PaymentInput | null;
}

export const ptApi = {
  plans: (includeHidden = false) =>
    request<PtPlan[]>(`/api/v1/pt/plans${includeHidden ? "?include_hidden=true" : ""}`),
  createPlan: (body: PtPlanInput) =>
    request<PtPlan>("/api/v1/pt/plans", send("POST", body)),
  updatePlan: (id: string, body: Partial<PtPlanInput>) =>
    request<PtPlan>(`/api/v1/pt/plans/${id}`, send("PATCH", body)),
  trainers: () => request<Trainer[]>("/api/v1/pt/trainers"),
  /** The signed-in trainer's own clients still to train. */
  clients: () => request<PtPackage[]>("/api/v1/pt/clients"),
  /** Every trainer's clients still to train, or one trainer's. */
  all: (trainerId?: string) =>
    request<PtPackage[]>(`/api/v1/pt/packages${query({ trainer_id: trainerId })}`),
  ofMember: (memberId: string) =>
    request<PtPackageDetail[]>(`/api/v1/members/${memberId}/pt`),
  sell: (memberId: string, body: PtSaleInput, key?: string) =>
    request<{ package: PtPackageDetail; payment: Payment | null }>(
      `/api/v1/members/${memberId}/pt`,
      once(send("POST", body), key),
    ),
  update: (
    id: string,
    body: {
      trainer_id?: string;
      start_date?: string;
      end_date?: string;
      reason?: string | null;
    },
  ) => request<PtPackageDetail>(`/api/v1/pt/packages/${id}`, send("PATCH", body)),
  cancel: (id: string, reason: string, refund: PaymentInput | null) =>
    request<PtPackageDetail>(
      `/api/v1/pt/packages/${id}/cancel`,
      send("POST", { reason, refund }),
    ),
  record: (
    id: string,
    body: { trained_on: string; note: string | null },
    key?: string,
  ) =>
    request<PtPackageDetail>(
      `/api/v1/pt/packages/${id}/sessions`,
      once(send("POST", body), key),
    ),
  voidSession: (sessionId: string, reason: string) =>
    request<PtPackageDetail>(
      `/api/v1/pt/sessions/${sessionId}/void`,
      send("POST", { reason }),
    ),
  /** Money towards it: an ordinary payment, with its own receipt. */
  collect: (packageId: string, payment: PaymentInput, key?: string) =>
    request<Payment>(
      "/api/v1/payments",
      once(send("POST", { pt_package_id: packageId, ...payment }), key),
    ),
};

// --- notifications for staff (PLAN.md §18.6) ---

export type NotificationKind = "payment_request" | "freeze_request" | "lead";

export interface StaffPushStatus {
  /** Null: push isn't set up on this server. */
  public_key: string | null;
  /** This browser, for this sign-in. */
  on_here: boolean;
  /** What this person may get, in order, and which of those they turned off. */
  kinds: NotificationKind[];
  muted: NotificationKind[];
}

export const staffPushApi = {
  status: (endpoint?: string) =>
    request<StaffPushStatus>(`/api/v1/auth/push${query({ endpoint })}`),
  on: (subscription: PushSubscriptionJSON) =>
    request<StaffPushStatus>(
      "/api/v1/auth/push",
      send("POST", { endpoint: subscription.endpoint, keys: subscription.keys }),
    ),
  resume: (endpoint: string) =>
    request<StaffPushStatus>("/api/v1/auth/push/resume", send("POST", { endpoint })),
  off: (endpoint: string) =>
    request<StaffPushStatus>("/api/v1/auth/push/off", send("POST", { endpoint })),
  choose: (muted: NotificationKind[], endpoint?: string) =>
    request<StaffPushStatus>(
      "/api/v1/auth/me/notifications",
      send("PUT", { muted, endpoint: endpoint ?? null }),
    ),
};

/** A member's "please freeze my membership" (PLAN.md §16.3, 8.6). */

export const freezeRequestsApi = {
  list: (status: FreezeRequest["status"] = "pending") =>
    request<FreezeRequest[]>(`/api/v1/freeze-requests${query({ status })}`),
  count: () => request<{ pending: number }>("/api/v1/freeze-requests/count"),
  approve: (id: string) =>
    request<FreezeRequest>(`/api/v1/freeze-requests/${id}/approve`, send("POST")),
  reject: (id: string, reason: string) =>
    request<FreezeRequest>(
      `/api/v1/freeze-requests/${id}/reject`,
      send("POST", { reason }),
    ),
};

// --- enquiries (PLAN.md §16.4, 9.1, 9.2, 9.6) ---

import { LEAD_SOURCES, type LeadSource } from "@shared/types";
export { LEAD_SOURCES, type LeadSource };
export const LEAD_STATUSES = ["new", "contacted", "trial", "joined", "lost"] as const;
export type LeadStatus = (typeof LEAD_STATUSES)[number];

export interface Lead {
  id: string;
  branch_id: string;
  name: string;
  phone: string | null;
  email: string | null;
  source: LeadSource;
  plan_id: string | null;
  status: LeadStatus;
  follow_up_on: string | null;
  lost_reason: string | null;
  assigned_to: string | null;
  trial_on: string | null;
  referred_by_id: string | null;
  member_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  plan_name: string | null;
  assigned_name: string | null;
  referred_by_name: string | null;
}

export interface LeadInput {
  name: string;
  phone?: string | null;
  email?: string | null;
  source?: LeadSource;
  branch_id?: string | null;
  plan_id?: string | null;
  follow_up_on?: string | null;
  assigned_to?: string | null;
  referred_by_id?: string | null;
  notes?: string | null;
}

export interface LeadMatch {
  id: string;
  name: string;
  kind: "member" | "lead";
  detail: string;
}

export interface SourceRow {
  source: LeadSource | "all";
  enquiries: number;
  trials: number;
  joined: number;
  conversion: number | null;
}

export interface LeadReport {
  first_day: string;
  last_day: string;
  rows: SourceRow[];
  total: SourceRow;
  top_referrers: {
    member_id: string;
    name: string;
    member_code: string;
    referred: number;
    joined: number;
  }[];
}

export const leadsApi = {
  list: (filters: { status?: LeadStatus; q?: string; source?: LeadSource } = {}) =>
    request<Lead[]>(`/api/v1/leads${query(filters)}`),
  get: (id: string) => request<Lead>(`/api/v1/leads/${id}`),
  create: (body: LeadInput) => request<Lead>("/api/v1/leads", send("POST", body)),
  update: (
    id: string,
    body: Partial<LeadInput> & { status?: LeadStatus; lost_reason?: string | null },
  ) => request<Lead>(`/api/v1/leads/${id}`, send("PATCH", body)),
  trial: (id: string) => request<Lead>(`/api/v1/leads/${id}/trial`, send("POST")),
  phoneCheck: (phone: string) =>
    request<LeadMatch[]>(`/api/v1/leads/phone-check${query({ phone })}`),
  report: (from?: string, to?: string) =>
    request<LeadReport>(`/api/v1/leads/report${query({ from, to })}`),
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
  resetTwoStep: (id: string) =>
    request<StaffMember>(`/api/v1/staff/${id}/two-step/reset`, send("POST")),
  signOutEverywhere: (id: string) =>
    request<{ signed_out: number }>(`/api/v1/staff/${id}/sign-out`, send("POST")),
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

/** What starts an automation (PLAN.md §16.3, 8.2; personal training's, §18.3). */
export type Trigger =
  "expiry" | "lapsed" | "dues" | "not_visiting" | "birthday" | "pt_ending" | "pt_dues";

export interface MessageSettings {
  welcome_sms: string;
  membership_sms: string;
  /** SMS as well as push, for members whose phone takes push (§16.3, 8.3). */
  also_sms: boolean;
}

export interface ReminderRule {
  id: string;
  trigger: Trigger;
  /** Meaning depends on the trigger: see components/automations/triggers.ts. */
  days: number;
  template: string;
  enabled: boolean;
}

export interface NoticeInput {
  title: string;
  body: string;
  branch_id?: string | null;
  send_sms: boolean;
}

/** Personal training with money still owed on it (§18.3). */
export interface PtOwing {
  package_id: string;
  member_id: string;
  name: string;
  phone: string;
  plan_name: string;
  trainer_name: string;
  end_date: string;
  dues: number;
}

/** Who to chase (PLAN.md §16.3, 8.1). Owing and not visiting: the first 100. */
export interface FollowUpLists {
  due_today: Member[];
  due_this_week: Member[];
  lapsed: Member[];
  owing: Member[];
  owing_total: number;
  /** Owed on personal training, apart from memberships (§18.3). */
  pt_owing: PtOwing[];
  pt_owing_total: number;
  not_visiting: Member[];
  not_visiting_total: number;
  not_visiting_days: number;
}

/** What a WhatsApp message from the desk is about (§18.5). */
export const MESSAGE_PURPOSES = [
  "reminder",
  "dues",
  "not_visiting",
  "welcome",
  "pt_dues",
] as const;
export type MessagePurpose = (typeof MESSAGE_PURPOSES)[number];

export const messagesApi = {
  followUp: () => request<FollowUpLists>("/api/v1/lists/follow-up"),
  smsLog: (memberId?: string) =>
    request<{ balance: number; items: SmsMessage[] }>(
      `/api/v1/sms${query({ member_id: memberId })}`,
    ),
  smsMember: (memberId: string, body: { reminder?: boolean; body?: string }) =>
    request<SmsMessage>(`/api/v1/members/${memberId}/sms`, send("POST", body)),
  /** The gym's wording for this member, to send on WhatsApp (§18.5). */
  memberMessage: (memberId: string, purpose: MessagePurpose) =>
    request<{ text: string; phone: string }>(
      `/api/v1/members/${memberId}/message${query({ purpose })}`,
    ),
  rules: () => request<ReminderRule[]>("/api/v1/reminder-rules"),
  createRule: (body: Omit<ReminderRule, "id">) =>
    request<ReminderRule>("/api/v1/reminder-rules", send("POST", body)),
  updateRule: (id: string, body: Partial<ReminderRule>) =>
    request<ReminderRule>(`/api/v1/reminder-rules/${id}`, send("PATCH", body)),
  deleteRule: (id: string) =>
    request<void>(`/api/v1/reminder-rules/${id}`, send("DELETE")),
  templates: () => request<MessageSettings>("/api/v1/sms-templates"),
  updateTemplates: (body: Partial<MessageSettings>) =>
    request<MessageSettings>("/api/v1/sms-templates", send("PATCH", body)),
  notices: () => request<Notice[]>("/api/v1/notices"),
  noticeCost: (body: NoticeInput) =>
    request<{
      recipients: number;
      /** Members whose phone takes push: free (PLAN.md §16.3, 8.3). */
      by_push: number;
      by_sms: number;
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
  /** A visit pack: left after this visit (§16.4, 9.3). */
  visits_left: number | null;
  can_override: boolean;
}

export type DeviceKind = "kiosk" | "zkteco" | "hikvision";
export type ReaderKind = Exclude<DeviceKind, "kiosk">;

export interface Device {
  id: string;
  branch_id: string;
  name: string;
  /** A kiosk, or a fingerprint and face reader (PLAN.md §18.2). */
  kind: DeviceKind;
  serial: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
  created_at: string;
  /** A reader's members on it, and changes not yet made there. */
  on_reader: number | null;
  waiting: number | null;
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
  /** A fingerprint or face reader; the token is for a Hikvision reader's bridge. */
  addReader: (body: {
    kind: ReaderKind;
    name: string;
    branch_id: string;
    serial: string | null;
  }) =>
    request<{ device: Device; token: string }>(
      "/api/v1/devices/readers",
      send("POST", body),
    ),
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
      /** [weekday][hour], Sunday first. */
      by_weekday_hour: number[][];
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
    key?: string,
  ) =>
    request<import("./memberApi").PaymentRequest>(
      `/api/v1/payment-requests/${id}/approve`,
      once(send("POST", body), key),
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
  signInLink: (id: string) =>
    request<SignInLink>(`/api/v1/members/${id}/sign-in-link`, send("POST")),
  card: (id: string) => request<CardInfo>(`/api/v1/members/${id}/card`),
  reissueCard: (id: string) =>
    request<CardInfo>(`/api/v1/members/${id}/card/reissue`, send("POST")),
};

// --- M4: Today, reports, data, subscription, platform admin ---------------------

export interface SetupChecklist {
  plans_priced: boolean;
  payment_account: boolean;
  logo: boolean;
  staff_invited: boolean;
  poster_printed: boolean;
  first_member: boolean;
}

export interface TodayData {
  date: string;
  check_ins: number;
  /** Let in, by hour of the day in Nepal: 24 counts. */
  check_ins_by_hour: number[];
  /** Yesterday up to this same time of day. */
  check_ins_yesterday: number;
  ending_today: { member_id: string; name: string; phone: string }[];
  top_owing: { member_id: string; name: string; dues: number }[];
  collected_yesterday: number | null;
  setup: SetupChecklist | null;
  leads_due: number | null;
  leads_due_list: {
    lead_id: string;
    name: string;
    phone: string | null;
    status: string;
    follow_up_on: string;
  }[];
  unique_visitors: number;
  inside_now: { member_id: string; name: string; at: string }[];
  due_today: number;
  expiring_this_week: number;
  not_visiting: number;
  turned_away: { member_id: string; name: string; at: string; result: string }[];
  members_with_dues: number;
  dues_total: number;
  active_members: number;
  collected: number | null;
  collected_by_method: Record<string, number> | null;
  pending_requests: number | null;
}

export interface MonthlyReport {
  month: string;
  calendar: "ad" | "bs";
  first_day: string;
  last_day: string;
  income: number;
  income_by_method: Record<string, number>;
  /** Spent (§18.1), and income less spent: below zero in a bad month. */
  expenses: number;
  expenses_by_category: Partial<Record<ExpenseCategory, number>>;
  profit: number;
  new_members: number;
  new_memberships: number;
  renewals: number;
  lapsed: number;
  due_to_renew: number;
  renewed: number;
  renewal_rate: number | null;
  active_members: number;
  visits: number;
  by_plan: Record<string, number>;
  /** Only for a gym with PT plans (§18.3). */
  personal_training: PtMonth | null;
}

/** Personal training in a report month (§18.3). */
export interface PtMonth {
  /** Already within the month's income. */
  income: number;
  sold: number;
  sessions: number;
  members: number;
  by_trainer: { trainer_id: string; name: string; members: number; sessions: number }[];
}

export interface TrendMonth {
  month: string;
  /** False before the gym joined: a gap on the charts, not a zero. */
  started: boolean;
  income: number;
  expenses: number;
  profit: number;
  new_members: number;
  renewals: number;
  lapsed: number;
  active_members: number;
  visits: number;
  renewal_rate: number | null;
}

export interface ImportPreview {
  id: string;
  filename: string;
  headers: string[];
  mapping: Record<string, number | null>;
  total_rows: number;
  sample: string[][];
  problems: [number, string][];
  ready: number;
  status: "preview" | "committed";
  result: { created: number; skipped: number; problems: [number, string][] } | null;
}

export interface PlatformPlan {
  id: string;
  name: string;
  max_active_members: number | null;
  max_branches: number | null;
  monthly_price: number | null;
  included_sms: number;
  is_active: boolean;
}

export interface SubscriptionPayment {
  id: string;
  gym_id: string;
  kind: "subscription" | "sms";
  platform_plan_id: string | null;
  months: number | null;
  sms_credits: number | null;
  amount: number;
  transaction_ref: string | null;
  status: "pending" | "approved" | "rejected";
  reject_reason: string | null;
  reviewed_at: string | null;
  created_at: string;
  gym_name: string | null;
  plan_name: string | null;
}

export interface SubscriptionOverview extends Omit<Subscription, "over_limit"> {
  active_members: number;
  max_active_members: number | null;
  over_limit: boolean;
  sms_balance: number;
  plans: PlatformPlan[];
  payments: SubscriptionPayment[];
  pay_to: { name: string | null; esewa: string | null; bank: string | null };
}

export interface AdminGym {
  id: string;
  slug: string;
  name: string;
  status: "active" | "suspended";
  owner_name: string | null;
  owner_phone: string | null;
  owner_email: string | null;
  owner_two_step: boolean;
  created_at: string;
  subscription_status: string;
  plan_name: string | null;
  ends_on: string | null;
  phase: Subscription["phase"];
  active_members: number;
  sms_balance: number;
  pending_payments: number;
  state: "trial" | "paying" | "grace" | "read_only" | "suspended";
  last_sign_in_at: string | null;
  check_ins_7d: number;
  members_added_30d: number;
  going_quiet: boolean;
  setup: Record<string, boolean>;
}

/** The /admin home (PLAN.md §16.5, 10.1). */
export interface AdminSummary {
  mrr: number;
  gyms: number;
  by_state: Record<AdminGym["state"], number>;
  trial_conversion: number | null;
  trials_ended: number;
  trials_converted: number;
  lost_by_month: { month: string; gyms: number }[];
  sms_sold_by_month: { month: string; credits: number; amount: number }[];
  going_quiet: number;
}

export interface ChangelogEntry {
  id: string;
  title: string;
  body: string;
  published_at: string | null;
  created_at: string;
}

export interface GymReferral {
  id: string;
  referrer_gym_id: string;
  referrer_name: string;
  referred_gym_id: string;
  referred_name: string;
  status: "pending" | "ready" | "rewarded" | "rejected";
  created_at: string;
  ready_at: string | null;
  note: string | null;
}

export interface MyReferrals {
  link: string;
  free_months: number;
  gyms: { name: string; status: GymReferral["status"]; joined_at: string }[];
}

export const changelogApi = {
  list: () => request<ChangelogEntry[]>("/api/v1/changelog"),
  seen: () => request<void>("/api/v1/changelog/seen", send("POST")),
};

export type ExportKind =
  "members" | "memberships" | "payments" | "expenses" | "check-ins";

export const reportsApi = {
  today: () => request<TodayData>("/api/v1/dashboard/today"),
  monthly: (month?: string) =>
    request<MonthlyReport>(`/api/v1/reports/monthly${query({ month })}`),
  trend: (end?: string) =>
    request<{ calendar: "ad" | "bs"; months: TrendMonth[] }>(
      `/api/v1/reports/trend${query({ end })}`,
    ),
  exportUrl: (kind: ExportKind) => `/api/v1/export/${kind}.xlsx`,
  /** Downloads through fetch, so the access token goes with it. */
  download: async (kind: ExportKind) => {
    const response = await fetch(`/api/v1/export/${kind}.xlsx`, {
      headers: staffAuthHeader(),
      credentials: "same-origin",
    });
    if (!response.ok) throw await toError(response);
    const blob = await response.blob();
    const name =
      /filename="([^"]+)"/.exec(
        response.headers.get("Content-Disposition") ?? "",
      )?.[1] ?? `${kind}.xlsx`;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    URL.revokeObjectURL(link.href);
  },
  uploadRegister: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<ImportPreview>("/api/v1/members/import", {
      method: "POST",
      body: form,
    });
  },
  previewRegister: (id: string, mapping: Record<string, number | null>) =>
    request<ImportPreview>(
      `/api/v1/members/import/${id}/preview`,
      send("POST", { mapping }),
    ),
  commitRegister: (id: string, mapping: Record<string, number | null>) =>
    request<ImportPreview>(
      `/api/v1/members/import/${id}/commit`,
      send("POST", { mapping }),
    ),
};

export const subscriptionApi = {
  overview: () => request<SubscriptionOverview>("/api/v1/subscription"),
  referrals: () => request<MyReferrals>("/api/v1/subscription/referrals"),
  pay: (
    body: {
      kind: "subscription" | "sms";
      platform_plan_id?: string | null;
      months?: number | null;
      sms_credits?: number | null;
      amount: number;
      transaction_ref: string;
    },
    key?: string,
  ) =>
    request<SubscriptionPayment>(
      "/api/v1/subscription/payments",
      once(send("POST", body), key),
    ),
};

export const adminApi = {
  summary: () => request<AdminSummary>("/api/v1/admin/summary"),
  changelog: () => request<ChangelogEntry[]>("/api/v1/admin/changelog"),
  addChangelog: (body: { title: string; body: string; published_at?: string | null }) =>
    request<ChangelogEntry>("/api/v1/admin/changelog", send("POST", body)),
  editChangelog: (
    id: string,
    body: { title?: string; body?: string; published_at?: string | null },
  ) => request<ChangelogEntry>(`/api/v1/admin/changelog/${id}`, send("PATCH", body)),
  deleteChangelog: (id: string) =>
    request<void>(`/api/v1/admin/changelog/${id}`, send("DELETE")),
  referrals: (status?: GymReferral["status"]) =>
    request<GymReferral[]>(`/api/v1/admin/gym-referrals${query({ status })}`),
  rewardReferral: (id: string) =>
    request<void>(`/api/v1/admin/gym-referrals/${id}/reward`, send("POST")),
  rejectReferral: (id: string, reason: string) =>
    request<void>(`/api/v1/admin/gym-referrals/${id}/reject`, send("POST", { reason })),
  gyms: (q?: string) => request<AdminGym[]>(`/api/v1/admin/gyms${query({ q })}`),
  grant: (
    id: string,
    body: { platform_plan_id?: string | null; months?: number; ends_on?: string },
  ) => request<AdminGym>(`/api/v1/admin/gyms/${id}/subscription`, send("POST", body)),
  credits: (id: string, credits: number, reason: string) =>
    request<AdminGym>(
      `/api/v1/admin/gyms/${id}/sms-credits`,
      send("POST", { credits, reason }),
    ),
  suspend: (id: string, reason: string) =>
    request<AdminGym>(`/api/v1/admin/gyms/${id}/suspend`, send("POST", { reason })),
  unsuspend: (id: string) =>
    request<AdminGym>(`/api/v1/admin/gyms/${id}/unsuspend`, send("POST")),
  ownerPassword: (id: string, new_password: string) =>
    request<void>(
      `/api/v1/admin/gyms/${id}/owner-password`,
      send("POST", { new_password }),
    ),
  resetOwnerTwoStep: (id: string) =>
    request<AdminGym>(`/api/v1/admin/gyms/${id}/owner-two-step`, send("POST")),
  payments: (status = "pending") =>
    request<SubscriptionPayment[]>(
      `/api/v1/admin/subscription-payments?status=${status}`,
    ),
  approve: (id: string) =>
    request<SubscriptionPayment>(
      `/api/v1/admin/subscription-payments/${id}/approve`,
      send("POST", {}),
    ),
  reject: (id: string, reason: string) =>
    request<SubscriptionPayment>(
      `/api/v1/admin/subscription-payments/${id}/reject`,
      send("POST", { reason }),
    ),
  plans: () => request<PlatformPlan[]>("/api/v1/admin/plans"),
  createPlan: (body: Partial<PlatformPlan>) =>
    request<PlatformPlan>("/api/v1/admin/plans", send("POST", body)),
  updatePlan: (id: string, body: Partial<PlatformPlan>) =>
    request<PlatformPlan>(`/api/v1/admin/plans/${id}`, send("PATCH", body)),
};
