/** Live events re-read the screens they affect, and only those (§17.3). */
import { invalidateFor, keys, queryClient } from "@/lib/query";

const SLUG = "fitness-zone";

function staleAfter(type: Parameters<typeof invalidateFor>[1]): string[] {
  queryClient.clear();
  const all = [
    keys.me(SLUG),
    keys.payments(SLUG),
    keys.renew(SLUG),
    keys.visits(SLUG, "2026-10"),
    keys.notices(SLUG),
    keys.freeze(SLUG),
    keys.me("other-gym"),
  ];
  for (const key of all) queryClient.setQueryData(key, {});
  invalidateFor(SLUG, type);
  return all
    .filter((key) => queryClient.getQueryState(key)?.isInvalidated)
    .map((key) => key.slice(0, 2).join("/"));
}

afterAll(() => queryClient.clear());

test.each([
  ["notice", ["fitness-zone/me", "fitness-zone/notices"]],
  ["check_in", ["fitness-zone/me", "fitness-zone/visits"]],
  [
    "payment_request",
    ["fitness-zone/me", "fitness-zone/payments", "fitness-zone/renew"],
  ],
  ["freeze_request", ["fitness-zone/me", "fitness-zone/freeze"]],
] as const)("%s", (type, expected) => {
  expect(staleAfter(type).sort()).toEqual([...expected].sort());
});

test("a resync re-reads everything of this gym, nothing of another", () => {
  const stale = staleAfter("resync");
  expect(stale).toHaveLength(6);
  expect(stale).not.toContain("other-gym/me");
});
