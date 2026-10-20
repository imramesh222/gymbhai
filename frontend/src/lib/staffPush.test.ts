import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resumeStaffPush, useStaffPush } from "./staffPush";

const { status, resume } = vi.hoisted(() => ({ status: vi.fn(), resume: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  staffPushApi: { status, resume },
}));

const ENDPOINT = "https://push.example.com/staff/1";

/** A browser that can take push, with or without a subscription for /staff. */
function browser(permission: NotificationPermission, subscribed: boolean) {
  const pushManager = {
    getSubscription: () => Promise.resolve(subscribed ? { endpoint: ENDPOINT } : null),
  };
  vi.stubGlobal("PushManager", function PushManager() {});
  vi.stubGlobal("Notification", { permission });
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { getRegistration: vi.fn(() => Promise.resolve({ pushManager })) },
  });
}

describe("staff notifications in the browser", () => {
  beforeEach(() => {
    status.mockReset().mockResolvedValue({
      public_key: "BKey",
      on_here: true,
      kinds: ["payment_request"],
      muted: [],
    });
    resume.mockReset().mockResolvedValue({});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "serviceWorker");
  });

  it("picks them up again after signing in, if this browser had them", async () => {
    browser("granted", true);
    await resumeStaffPush();
    expect(resume).toHaveBeenCalledWith(ENDPOINT);
  });

  it("never asks, and never resumes a browser that wasn't turned on", async () => {
    browser("default", true);
    await resumeStaffPush();
    browser("granted", false);
    await resumeStaffPush();
    expect(resume).not.toHaveBeenCalled();
  });

  it("is on only for this browser's own sign-in", async () => {
    browser("granted", true);
    const { result } = renderHook(() => useStaffPush());
    await waitFor(() => expect(result.current.state).toBe("on"));
    expect(status).toHaveBeenCalledWith(ENDPOINT);

    status.mockResolvedValue({
      public_key: "BKey",
      on_here: false,
      kinds: ["payment_request"],
      muted: [],
    });
    const again = renderHook(() => useStaffPush());
    await waitFor(() => expect(again.result.current.state).toBe("off"));
  });

  it("blocked, or not set up on the server", async () => {
    browser("denied", true);
    const blocked = renderHook(() => useStaffPush());
    await waitFor(() => expect(blocked.result.current.state).toBe("blocked"));

    browser("granted", false);
    status.mockResolvedValue({
      public_key: null,
      on_here: false,
      kinds: [],
      muted: [],
    });
    const unset = renderHook(() => useStaffPush());
    await waitFor(() => expect(unset.result.current.state).toBe("unavailable"));
  });
});
