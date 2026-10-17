import type { Plan } from "@/lib/api";

/**
 * What a longer plan is worth against paying month by month (PLAN.md §16.3,
 * 8.5): "Rs 1,333 a month — save Rs 500". Only plans counted in months;
 * day passes have no monthly price.
 */
export function perMonth(plan: Plan): number | null {
  if (plan.price === null || !plan.duration_months) return null;
  return Math.round(plan.price / plan.duration_months);
}

/** Against the cheapest one-month plan; null when there is none to compare. */
export function savings(plan: Plan, plans: Plan[]): number | null {
  if (plan.price === null || !plan.duration_months || plan.duration_months < 2) {
    return null;
  }
  const monthly = plans
    .filter((p) => p.duration_months === 1 && p.price !== null)
    .map((p) => p.price as number);
  if (monthly.length === 0) return null;
  const saved = Math.min(...monthly) * plan.duration_months - plan.price;
  return saved > 0 ? saved : null;
}
