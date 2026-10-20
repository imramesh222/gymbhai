import { describe, expect, it } from "vitest";

import { sign, verify } from "./ed25519";
import { hmacSha256, sha256, toHex, utf8 } from "./hmac";
import { memberCode, parseCode, signature, verifyCode2 } from "./memberQr";

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

describe("gb2: the member QR a kiosk can check offline (PLAN.md §19.2)", () => {
  // The same vector as backend/tests/unit/test_qr.py.
  const member = "12345678123456781234567812345678";
  const identity = {
    member_hex: member,
    key: "P-5VXu9nLNLOU1OTAEFX9jwIldfaTzZeyqhp38H3WLg",
    version: 1,
    window_seconds: 30,
    signing_key: "mtbJK1LD-vbZuDVIEk8nqscuQojfRzEG9KZys-cjASc",
  };
  const publicKey = "p6tHitkllt09ERnscZwAyjqc2nL8DGBHkUO5H1VwTfQ";
  const at = 59_666_666 * 30 * 1000 + 5_000;
  const expected =
    `gb2.${member}.59666666.` +
    "na-qDqQPKYTID_k4B7bDXQjSYeixck8XrS4Ig5B5D6eydcFyeyP8B3SX6BHZDMAsXtSKkWCrVtbG4HbpV4YYAw";

  it("signs the code the server checks", () => {
    expect(memberCode(identity, at, sign)).toBe(expected);
    // Without Ed25519, or a key saved before gb2: still gb1.
    expect(memberCode(identity, at)).toMatch(/^gb1\./);
  });

  it("is checked with the public key alone, within a window either side", () => {
    const scanned = parseCode(expected)!;
    expect(scanned.kind).toBe("app2");
    expect(verifyCode2(scanned, publicKey, verify, at)).toBe(true);
    expect(verifyCode2(scanned, publicKey, verify, at + 30_000)).toBe(true);
    expect(verifyCode2(scanned, publicKey, verify, at + 90_000)).toBe(false);
    const forged = parseCode(expected.slice(0, -2) + "AA")!;
    expect(verifyCode2(forged, publicKey, verify, at)).toBe(false);
  });

  it("reads cards and turns junk away", () => {
    expect(parseCode("gbc.abcDEF123456")).toEqual({
      kind: "card",
      card_token: "abcDEF123456",
    });
    for (const junk of ["", "hello", "gb1.x.y.z", "gb2.a.b.c", "gbc.", "https://x.y"])
      expect(parseCode(junk)).toBeNull();
  });
});
