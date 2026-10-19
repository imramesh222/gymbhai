import { describe, expect, it } from "vitest";

import { deskToken } from "./deskLink";

const TOKEN = "Q2xlYW5fdG9rZW4tZm9yLXRlc3Rz";

describe("the desk's sign-in QR", () => {
  it("finds the token after #desk=", () => {
    expect(deskToken(`https://app.gymbhai.com/fitness-zone#desk=${TOKEN}`)).toBe(TOKEN);
    expect(deskToken(`http://192.168.1.20:3000/fitness-zone#x=1&desk=${TOKEN}`)).toBe(
      TOKEN,
    );
  });

  it("ignores every other link", () => {
    expect(deskToken("https://app.gymbhai.com/fitness-zone")).toBeNull();
    expect(deskToken("https://app.gymbhai.com/fitness-zone?b=1")).toBeNull();
    // In the query it would reach the server's logs: not ours.
    expect(deskToken(`https://app.gymbhai.com/fitness-zone?desk=${TOKEN}`)).toBeNull();
    expect(deskToken("https://app.gymbhai.com/fitness-zone#desk=short")).toBeNull();
    expect(deskToken(`https://x.example/#desk=${TOKEN}<script>`)).toBeNull();
    expect(deskToken("gb1.abc.123.sig")).toBeNull();
  });
});
