/**
 * Enter moves to the next field instead of saving half a form: the desk
 * types name, Enter, phone, Enter… (PLAN.md §16.2, 7.7). On the last field,
 * or on a button, Enter does what it always does.
 */
export function enterMovesOn(event: React.KeyboardEvent<HTMLFormElement>) {
  if (event.key !== "Enter" || event.shiftKey) return;
  const target = event.target as HTMLElement;
  if (!(target instanceof HTMLInputElement) || target.type === "checkbox") return;
  const fields = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>(
      "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])",
    ),
  ).filter((field) => field.offsetParent !== null);
  const next = fields[fields.indexOf(target) + 1];
  if (!next) return;
  event.preventDefault();
  next.focus();
}
