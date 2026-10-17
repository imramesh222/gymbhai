/** The API client: refresh once for many, retries only when safe (§17.2, §17.4). */
import * as SecureStore from "expo-secure-store";

import {
  ApiError,
  freshAccessToken,
  keepSession,
  NetworkError,
  request,
  selectGym,
  setSessionHandlers,
} from "@/lib/api";
import { resetClock, serverNow } from "@/lib/clock";

type Call = { url: string; init: RequestInit };
let calls: Call[];
let answers: ((call: Call) => Response | Promise<Response>)[];

function json(status: number, body: unknown, date?: string): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: date ? { date } : {},
  });
}

beforeEach(async () => {
  calls = [];
  answers = [];
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const call = { url: String(url), init: init ?? {} };
    calls.push(call);
    const answer = answers.shift();
    if (!answer) throw new TypeError("Network request failed");
    return answer(call);
  }) as typeof fetch;
  selectGym(null);
  selectGym("fitness-zone");
  await keepSession("fitness-zone", {
    access_token: "old-access",
    expires_in: 900,
    refresh_token: "refresh-token-0000000001",
    me: null,
    choose: null,
  });
  resetClock();
});

const header = (call: Call, name: string) =>
  (call.init.headers as Record<string, string>)[name];

test("two requests that find the token expired share one refresh", async () => {
  answers = [
    () => json(401, { code: "token_expired" }),
    () => json(401, { code: "token_expired" }),
    () =>
      json(200, {
        access_token: "new-access",
        expires_in: 900,
        refresh_token: "refresh-token-0000000002",
        me: null,
        choose: null,
      }),
    () => json(200, { ok: 1 }),
    () => json(200, { ok: 2 }),
  ];
  const results = await Promise.all([request("/a"), request("/b")]);
  expect(results).toEqual([{ ok: 1 }, { ok: 2 }]);
  const refreshes = calls.filter((c) => c.url.endsWith("/auth/refresh"));
  expect(refreshes).toHaveLength(1);
  expect(JSON.parse(String(refreshes[0].init.body))).toEqual({
    refresh_token: "refresh-token-0000000001",
  });
  expect(await SecureStore.getItemAsync("refresh.fitness-zone")).toBe(
    "refresh-token-0000000002",
  );
  expect(header(calls[3], "Authorization")).toBe("Bearer new-access");
});

test("a refused refresh ends the session; no signal does not", async () => {
  const lost: string[] = [];
  setSessionHandlers({ lost: (slug) => lost.push(slug), refreshed: null });
  answers = [() => json(401, { code: "token_expired" })]; // then no answer
  await expect(request("/a")).rejects.toBeInstanceOf(NetworkError);
  expect(lost).toEqual([]);
  expect(await SecureStore.getItemAsync("refresh.fitness-zone")).not.toBeNull();

  answers = [() => json(401, { code: "session_ended" })];
  await expect(freshAccessToken()).resolves.toBeNull();
  expect(lost).toEqual(["fitness-zone"]);
  expect(await SecureStore.getItemAsync("refresh.fitness-zone")).toBeNull();
  setSessionHandlers({ lost: null, refreshed: null });
});

test("a keyed write is retried after no answer, with the same key", async () => {
  answers = [
    () => {
      throw new TypeError("Network request failed");
    },
    () => json(201, { id: "r1" }),
  ];
  const result = await request("/api/v1/m/payment-requests", {
    body: { plan_id: "p" },
    idempotencyKey: "renew-key-0001",
  });
  expect(result).toEqual({ id: "r1" });
  expect(calls).toHaveLength(2);
  expect(calls.map((c) => header(c, "Idempotency-Key"))).toEqual([
    "renew-key-0001",
    "renew-key-0001",
  ]);
});

test("a write without a key is never sent twice by the client", async () => {
  answers = [];
  await expect(request("/api/v1/m/me/photo", { body: {} })).rejects.toBeInstanceOf(
    NetworkError,
  );
  expect(calls).toHaveLength(1);
});

test("errors carry the API's code and fields", async () => {
  answers = [
    () =>
      json(422, {
        code: "validation_error",
        detail: "Bad",
        fields: [{ field: "amount", type: "x" }],
      }),
  ];
  const error = (await request("/x", { body: {}, idempotencyKey: "k-00000001" }).catch(
    (e) => e,
  )) as ApiError;
  expect(error).toBeInstanceOf(ApiError);
  expect(error.code).toBe("validation_error");
  expect(error.fields[0].field).toBe("amount");
});

test("the Date header corrects the clock the QR is drawn with", async () => {
  const fiveMinutesAhead = new Date(Date.now() + 5 * 60_000).toUTCString();
  answers = [() => json(200, {}, fiveMinutesAhead)];
  await request("/a");
  expect(serverNow() - Date.now()).toBeGreaterThan(4 * 60_000);
  expect(serverNow() - Date.now()).toBeLessThan(6 * 60_000);
});
