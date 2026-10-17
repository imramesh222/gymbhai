import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { newIdempotencyKey, useIdempotencyKey } from "./idempotency";

describe("idempotency keys", () => {
  it("are random and fit the API's rules", () => {
    const key = newIdempotencyKey();
    expect(key).toMatch(/^[0-9a-f]{32}$/);
    expect(newIdempotencyKey()).not.toBe(key);
  });

  it("stay the same while the same thing is sent again", () => {
    const { result } = renderHook(() => useIdempotencyKey());
    const first = result.current.keyFor({ amount: 500 });
    expect(result.current.keyFor({ amount: 500 })).toBe(first);
  });

  it("change when what is sent changes, and after a success", () => {
    const { result } = renderHook(() => useIdempotencyKey());
    const first = result.current.keyFor({ amount: 500 });
    const changed = result.current.keyFor({ amount: 400 });
    expect(changed).not.toBe(first);
    result.current.succeeded();
    expect(result.current.keyFor({ amount: 400 })).not.toBe(changed);
  });
});
