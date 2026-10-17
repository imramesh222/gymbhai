/** Grey shapes where content is coming, instead of a blank page. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`block animate-pulse rounded-lg bg-slate-200/80 ${className}`}
    />
  );
}

/** A loading page: a heading, a row of numbers and a list. */
export function PageSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-5">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((n) => (
          <Skeleton key={n} className="h-24 rounded-2xl" />
        ))}
      </div>
      <ListSkeleton />
    </div>
  );
}

/** Rows of a list while it loads. */
export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
      {Array.from({ length: rows }, (_, n) => (
        <div key={n} className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}
