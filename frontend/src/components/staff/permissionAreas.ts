/**
 * The order of the staff form's permission checklist (PLAN.md §2.1). An
 * area the catalog has and this list lacks still shows, at the end, so no
 * permission is ever left off the form.
 */
const AREAS = [
  "members",
  "leads",
  "memberships",
  "pt",
  "classes",
  "progress",
  "payments",
  "expenses",
  "shop",
  "reports",
  "door",
  "messages",
  "setup",
  "staff",
];

export function areasOf(catalog: { permissions: { area: string }[] }): string[] {
  const extra = catalog.permissions
    .map((p) => p.area)
    .filter((area) => !AREAS.includes(area));
  return [...AREAS, ...new Set(extra)];
}
