import { formatRs } from "@/lib/money";

/**
 * An amount on screen, never broken over two lines after "Rs". `smallUnit`
 * sets "Rs" smaller, for a big figure in a narrow tile.
 */
export function Money({
  paisa,
  className = "",
  smallUnit = false,
}: {
  paisa: number | null;
  className?: string;
  smallUnit?: boolean;
}) {
  const text = formatRs(paisa);
  const parts = smallUnit ? /^(−?)(\S+) (.+)$/.exec(text) : null;
  if (!parts)
    return (
      <span className={`whitespace-nowrap tabular-nums ${className}`}>{text}</span>
    );
  const [, sign, unit, amount] = parts;
  return (
    <span className={`whitespace-nowrap tabular-nums ${className}`}>
      {sign}
      <span className="text-[0.6em] font-semibold">{unit}</span>
      {"\u00a0"}
      {amount}
    </span>
  );
}
