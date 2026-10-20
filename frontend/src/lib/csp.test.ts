import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, newNonce } from "./csp";

function directives(policy: string): Record<string, string> {
  return Object.fromEntries(
    policy.split("; ").map((d) => {
      const [name, ...values] = d.split(" ");
      return [name, values.join(" ")];
    }),
  );
}

describe("the content security policy", () => {
  it("runs scripts only with this request's nonce", () => {
    const policy = directives(contentSecurityPolicy("abc123", false));
    expect(policy["script-src"]).toBe("'self' 'nonce-abc123' 'strict-dynamic'");
    expect(policy["script-src"]).not.toContain("unsafe-inline");
    expect(policy["script-src"]).not.toContain("unsafe-eval");
  });

  it("can't be framed and loads nothing from elsewhere", () => {
    const policy = directives(contentSecurityPolicy("abc123", false));
    expect(policy["frame-ancestors"]).toBe("'none'");
    expect(policy["object-src"]).toBe("'none'");
    expect(policy["default-src"]).toBe("'self'");
    expect(policy["connect-src"]).toBe("'self'");
  });

  it("posts forms to us, and to eSewa's checkout only", () => {
    const policy = directives(contentSecurityPolicy("abc123", false));
    expect(policy["form-action"]).toBe(
      "'self' https://epay.esewa.com.np https://rc-epay.esewa.com.np",
    );
  });

  it("allows what the dev server needs, only in development", () => {
    const policy = directives(contentSecurityPolicy("abc123", true));
    expect(policy["script-src"]).toContain("'unsafe-eval'");
    expect(policy["connect-src"]).toBe("'self' ws: wss:");
  });

  it("makes a new nonce each time", () => {
    expect(newNonce()).not.toBe(newNonce());
  });
});
