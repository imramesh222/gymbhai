/**
 * A class's colour (PLAN.md §19.4), as a dot beside its name on the
 * timetable, the desk's week and the member's app. Strong enough to read on
 * white; the name always says what it is, so colour is never the only cue.
 */
export const CLASS_COLOR_HEX: Record<string, string> = {
  blue: "#2563eb",
  teal: "#0d9488",
  green: "#16a34a",
  amber: "#d97706",
  orange: "#ea580c",
  red: "#dc2626",
  pink: "#db2777",
  purple: "#7c3aed",
};

export function classColor(name: string): string {
  return CLASS_COLOR_HEX[name] ?? CLASS_COLOR_HEX.blue;
}
