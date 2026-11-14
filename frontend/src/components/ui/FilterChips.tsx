export interface Chip<K extends string> {
  key: K;
  label: string;
  /** A count beside the label: "Expired 55". */
  count?: number;
}

/**
 * A row of filters where one is on. On a phone the row scrolls sideways
 * instead of wrapping, and no label breaks over two lines.
 */
export function FilterChips<K extends string>({
  label,
  chips,
  value,
  onChange,
  className = "",
}: {
  /** What the row filters, for screen readers. */
  label: string;
  chips: Chip<K>[];
  /** The chip that is on; null when none of them is. */
  value: K | null;
  onChange: (key: K) => void;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      // A pixel of room all round: a scrolling row would cut the chips' rings.
      className={`no-scrollbar -mx-px flex gap-2 overflow-x-auto px-px pt-px pb-1 ${className}`}
    >
      {chips.map((chip) => {
        const active = chip.key === value;
        return (
          <button
            key={chip.key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(chip.key)}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium whitespace-nowrap transition ${
              active
                ? "bg-brand-600 text-white shadow-brand"
                : "bg-white text-slate-600 shadow-card ring-1 ring-hairline hover:bg-slate-50"
            }`}
          >
            {chip.label}
            {chip.count !== undefined && (
              <>
                {" "}
                <span className={active ? "text-white/80" : "text-slate-500"}>
                  {chip.count}
                </span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
