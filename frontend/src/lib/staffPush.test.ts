import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resumeStaffPush, useStaffPush } from "./staffPush";

const { status, resume, on } = vi.hoisted(() => ({
  status: vi.fn(),
  resume: vi.fn(),
  on: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  staffPushApi: { status, resume, on },
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
    on.mockReset().mockResolvedValue({
      public_key: "BKey",
      on_here: true,
      kinds: ["payment_request"],
      muted: [],
    });
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

  it("turns on the first time, while the new worker is still installing", async () => {
    // A browser that never had them: no /staff worker until "Turn on", and
    // like Chrome, no subscription until that worker is running.
    const changes: (() => void)[] = [];
    const worker = {
      state: "installing",
      addEventListener: (_: string, change: () => void) => changes.push(change),
    };
    const fresh = { endpoint: ENDPOINT, toJSON: () => ({ endpoint: ENDPOINT }) };
    const reg = {
      active: null as typeof worker | null,
      installing: worker,
      waiting: null,
      pushManager: {
        getSubscription: () => Promise.resolve(null),
        subscribe: vi.fn(() =>
          reg.active
            ? Promise.resolve(fresh)
            : Promise.reject(new Error("Subscription failed - no active Service Worker")),
        ),
      },
    };
    vi.stubGlobal("PushManager", function PushManager() {});
    vi.stubGlobal("Notification", {
      permission: "default",
      requestPermission: () => Promise.resolve("granted"),
    });
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        getRegistration: vi.fn(() => Promise.resolve(undefined)),
        register: vi.fn(() => Promise.resolve(reg)),
      },
    });
    status.mockResolvedValue({
      public_key: "BKey",
      on_here: false,
      kinds: ["payment_request"],
      muted: [],
    });

    const { result } = renderHook(() => useStaffPush());
    await waitFor(() => expect(result.current.state).toBe("off"));
    let turning: Promise<void> = Promise.resolve();
    act(() => {
      turning = result.current.on();
    });
    await waitFor(() => expect(changes).toHaveLength(1));
    expect(reg.pushManager.subscribe).not.toHaveBeenCalled();

    worker.state = "activated";
    reg.active = worker;
    await act(async () => {
      changes.forEach((change) => change());
      await turning;
    });
    expect(result.current.error).toBeNull();
    expect(result.current.state).toBe("on");
    expect(on).toHaveBeenCalledWith({ endpoint: ENDPOINT });
  });
});
