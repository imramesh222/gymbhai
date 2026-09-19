import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, errorMessage, refreshSession, request, setAccessToken } from "./api";

function reply(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const session = (token: string) => ({
  access_token: token,
  token_type: "bearer",
  expires_in: 900,
  me: {},
});

describe("request", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setAccessToken("old-token");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setAccessToken(null);
  });

  it("sends the access token", async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { ok: true }));
    await request("/api/v1/gym");
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer old-token");
  });

  it("refreshes once on a 401 and retries with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(reply(401, { code: "session_expired" }))
      .mockResolvedValueOnce(reply(200, session("new-token")))
      .mockResolvedValueOnce(reply(200, { name: "Fitness Zone" }));

    await expect(request("/api/v1/gym")).resolves.toEqual({ name: "Fitness Zone" });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/auth/refresh");
    const retry = fetchMock.mock.calls[2][1].headers as Headers;
    expect(retry.get("Authorization")).toBe("Bearer new-token");
  });

  it("gives up when the refresh fails", async () => {
    fetchMock
      .mockResolvedValueOnce(reply(401, { code: "session_expired" }))
      .mockResolvedValueOnce(reply(401, { code: "session_ended" }));
    await expect(request("/api/v1/gym")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shares one refresh between concurrent callers", async () => {
    fetchMock.mockResolvedValue(reply(200, session("t")));
    await Promise.all([refreshSession(), refreshSession(), refreshSession()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("turns API errors into ApiError with the code", async () => {
    fetchMock.mockResolvedValueOnce(
      reply(409, { detail: "That gym address is already taken.", code: "slug_taken" }),
    );
    const error = (await request("/x", { method: "POST" }).catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("slug_taken");
  });
});

describe("errorMessage", () => {
  it("translates by code, not by the English detail", () => {
    const error = new ApiError(409, "slug_taken", "anything");
    expect(errorMessage(error)).toBe("That gym address is already taken. Try another.");
  });

  it("names the fields that need attention", () => {
    const error = new ApiError(422, "validation_error", "x", [
      { field: "owner_phone", type: "value_error" },
      { field: "password", type: "string_too_short" },
    ]);
    expect(errorMessage(error)).toBe("Please check: Mobile number, Password.");
  });

  it("falls back to the server's message for unknown codes", () => {
    expect(errorMessage(new ApiError(400, "brand_new", "Server says"))).toBe(
      "Server says",
    );
  });
});
