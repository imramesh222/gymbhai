/**
 * Talking to the API (PLAN.md §17.2).
 *
 * - The access token lives in memory; the refresh token in the phone's
 *   secure storage, one per gym (a member of two gyms has two sessions).
 * - An expired access token is renewed once, transparently; two screens
 *   asking at once share one refresh, so a rotated token is never used twice.
 * - A dropped connection is retried for reads, and for writes that carry an
 *   Idempotency-Key: the server does those once however often they arrive.
 * - "Signed out" only when the server says so; no signal is not signed out.
 */
import * as SecureStore from "expo-secure-store";

import type { MemberSignIn } from "@shared/types";

import { observe } from "./clock";
import { API_URL, USER_AGENT } from "./config";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: { field: string; type: string }[] = [],
    readonly extra: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** No answer at all: no signal, or the server can't be reached. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super("network");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  form?: FormData;
  /** Makes a write safe to send again (PLAN.md §17.4). */
  idempotencyKey?: string;
  /** False for the routes used before signing in. */
  auth?: boolean;
}

// --- the session -----------------------------------------------------------------

let gym: string | null = null;
let access: { token: string; expiresAt: number } | null = null;
let refreshing: Promise<MemberSignIn | null> | null = null;
let onSessionLost: ((slug: string) => void) | null = null;
let onSignedIn: ((result: MemberSignIn) => void) | null = null;

/** SecureStore keys allow [A-Za-z0-9._-]; gym addresses are slugs. */
const tokenKey = (slug: string) => `refresh.${slug}`;

export function selectGym(slug: string | null) {
  if (slug !== gym) access = null;
  gym = slug;
}

export function currentGym(): string | null {
  return gym;
}

export function setSessionHandlers(handlers: {
  lost: ((slug: string) => void) | null;
  refreshed: ((result: MemberSignIn) => void) | null;
}) {
  onSessionLost = handlers.lost;
  onSignedIn = handlers.refreshed;
}

export async function hasSession(slug: string): Promise<boolean> {
  return Boolean(await SecureStore.getItemAsync(tokenKey(slug)));
}

/** After signing in, or a refresh: keep what the server gave us. */
export async function keepSession(slug: string, result: MemberSignIn): Promise<void> {
  if (result.refresh_token) {
    await SecureStore.setItemAsync(tokenKey(slug), result.refresh_token);
  }
  if (slug === gym && result.access_token) {
    access = {
      token: result.access_token,
      expiresAt: Date.now() + (result.expires_in ?? 900) * 1000,
    };
  }
}

export async function forgetSession(slug: string): Promise<void> {
  await SecureStore.deleteItemAsync(tokenKey(slug));
  if (slug === gym) access = null;
}

export async function refreshToken(slug: string): Promise<string | null> {
  return SecureStore.getItemAsync(tokenKey(slug));
}

/**
 * Swap the refresh token for a new pair. Null when the server says the
 * session is over; a NetworkError when it can't be asked.
 */
export function refreshSession(): Promise<MemberSignIn | null> {
  const slug = gym;
  if (!slug) return Promise.resolve(null);
  refreshing ??= (async () => {
    try {
      const token = await SecureStore.getItemAsync(tokenKey(slug));
      if (!token) return null;
      const response = await send("/api/v1/m/auth/refresh", {
        method: "POST",
        body: { refresh_token: token },
      });
      if (response.status === 401 || response.status === 403) {
        await forgetSession(slug);
        onSessionLost?.(slug);
        return null;
      }
      const result = (await parse(response)) as MemberSignIn;
      await keepSession(slug, result);
      onSignedIn?.(result);
      return result;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/**
 * An access token good for at least `minSeconds` more, refreshing if need be.
 * Null when signed out. Throws NetworkError when offline and none is held.
 */
export async function freshAccessToken(
  minSeconds = 30,
): Promise<{ token: string; expiresAt: number } | null> {
  if (access && access.expiresAt - Date.now() > minSeconds * 1000) return access;
  const result = await refreshSession();
  return result && access ? access : null;
}

// --- requests --------------------------------------------------------------------

async function send(path: string, options: RequestOptions, token?: string | null) {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "User-Agent": USER_AGENT,
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  const sentAt = Date.now();
  let response: Response;
  try {
    response = await fetch(API_URL + path, {
      method: options.method ?? (options.body || options.form ? "POST" : "GET"),
      headers,
      body:
        options.form ??
        (options.body === undefined ? undefined : JSON.stringify(options.body)),
    });
  } catch (error) {
    throw new NetworkError(error);
  }
  observe(response.headers.get("date"), sentAt, Date.now());
  return response;
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  const data = text ? safeJson(text) : undefined;
  if (response.ok) return data;
  // The API's errors: {"code": ..., "detail": ..., "fields": [...], ...extra}.
  const { code, detail, fields, ...extra } = (data ?? {}) as {
    code?: string;
    detail?: unknown;
    fields?: unknown;
  };
  // A proxy's 502 while the server restarts is "try again", like no signal.
  if (response.status >= 502 && response.status <= 504 && !code) {
    throw new NetworkError(response.status);
  }
  throw new ApiError(
    response.status,
    code ?? `http_${response.status}`,
    typeof detail === "string" ? detail : "",
    Array.isArray(fields) ? fields : [],
    extra,
  );
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

const RETRY_DELAYS_MS = [400, 1500];
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Reads, and writes with a key, are safe to send again after no answer. */
async function withRetry<T>(retryable: boolean, attempt: () => Promise<T>): Promise<T> {
  for (let i = 0; ; i++) {
    try {
      return await attempt();
    } catch (error) {
      if (
        !(error instanceof NetworkError) ||
        !retryable ||
        i >= RETRY_DELAYS_MS.length
      ) {
        throw error;
      }
      await sleep(RETRY_DELAYS_MS[i]);
    }
  }
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const retryable =
    (options.method ?? "GET") === "GET" && !options.body && !options.form
      ? true
      : Boolean(options.idempotencyKey);
  if (options.auth === false) {
    return (await parse(await withRetry(retryable, () => send(path, options)))) as T;
  }
  const first = await freshAccessToken();
  if (!first) throw new ApiError(401, "session_ended", "");
  let response = await withRetry(retryable, () => send(path, options, first.token));
  if (response.status === 401) {
    // Revoked or expired early: one refresh, then the same request again
    // (with the same key, so a write that did land isn't done twice).
    access = null;
    const again = await freshAccessToken();
    if (!again) throw new ApiError(401, "session_ended", "");
    response = await withRetry(retryable, () => send(path, options, again.token));
  }
  return (await parse(response)) as T;
}
