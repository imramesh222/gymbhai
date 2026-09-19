import { formatRs } from "@/lib/money";

export function Money({
  paisa,
  className = "",
}: {
  paisa: number | null;
  className?: string;
}) {
  return <span className={`tabular-nums ${className}`}>{formatRs(paisa)}</span>;
}
