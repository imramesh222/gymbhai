import { describe, expect, it } from "vitest";

import { hmacSha256, sha256, toHex, utf8 } from "./hmac";
import { memberCode, signature } from "./memberQr";

describe("sha256", () => {
  it("matches the standard vectors", () => {
    expect(toHex(sha256(utf8("")))).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
    expect(toHex(sha256(utf8("abc")))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    // Crosses a block boundary.
    expect(toHex(sha256(utf8("a".repeat(1000))))).toBe(
      "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3",
    );
  });
});

describe("hmacSha256", () => {
  it("matches RFC 4231 test case 2", () => {
    expect(toHex(hmacSha256(utf8("Jefe"), utf8("what do ya want for nothing?")))).toBe(
      "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
    );
  });
});

describe("member QR codes match the backend", () => {
  // The same vector as backend/tests/unit/test_qr.py.
  const key = "P-5VXu9nLNLOU1OTAEFX9jwIldfaTzZeyqhp38H3WLg";
  const member = "12345678123456781234567812345678";

  it("signs a window the way the server checks it", () => {
    expect(signature(key, member, 59_666_666)).toBe("uD4CqX4EAlGpxzdJ");
  });

  it("builds the whole code for the current window", () => {
    const at = 59_666_666 * 30 * 1000 + 5_000;
    expect(
      memberCode({ member_hex: member, key, version: 1, window_seconds: 30 }, at),
    ).toBe(`gb1.${member}.59666666.uD4CqX4EAlGpxzdJ`);
  });
});
