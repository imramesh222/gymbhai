import { describe, expect, it } from "vitest";

import { describeDevice } from "./userAgent";

describe("describeDevice", () => {
  it.each([
    [
      "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36",
      "Chrome",
      "Android",
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
      "Safari",
      "iPhone",
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0",
      "Edge",
      "Windows",
    ],
    [
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:132.0) Gecko/20100101 Firefox/132.0",
      "Firefox",
      "Mac",
    ],
    [
      "Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0 Mobile Safari/537.36",
      "Samsung Internet",
      "Android",
    ],
  ])("%s", (ua, browser, system) => {
    expect(describeDevice(ua)).toEqual({ browser, system });
  });

  it("knows nothing about an empty one", () => {
    expect(describeDevice(null)).toEqual({ browser: null, system: null });
  });
});
