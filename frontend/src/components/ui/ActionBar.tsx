/**
 * The bar at the foot of a long form: the total and Save stay in reach while
 * the person scrolls. Above the phone's tab bar, below dialogs.
 */
export function ActionBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="sticky bottom-16 z-10 -mx-4 mt-4 border-t border-hairline bg-surface/95 px-4 py-3 backdrop-blur-md sm:mx-0 sm:rounded-2xl sm:border-0 sm:shadow-raised sm:ring-1 sm:ring-hairline lg:bottom-4 print:hidden">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {children}
      </div>
    </div>
  );
}
