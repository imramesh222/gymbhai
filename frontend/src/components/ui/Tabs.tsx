"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useRef } from "react";

export interface Tab {
  id: string;
  label: string;
  /** A count beside the label: "Payments 3". */
  count?: number;
}

/**
 * Tabs kept in the address (?tab=payments): a tab can be linked to, and a
 * refresh lands on it. Arrow keys move between them.
 */
export function useTab(tabs: Tab[], param = "tab"): string {
  const wanted = useSearchParams().get(param);
  return tabs.some((tab) => tab.id === wanted) ? wanted! : tabs[0].id;
}

export function Tabs({
  tabs,
  label,
  param = "tab",
  children,
}: {
  tabs: Tab[];
  label: string;
  param?: string;
  /** The panel for the current tab. */
  children: React.ReactNode;
}) {
  const current = useTab(tabs, param);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const id = useId();
  const list = useRef<HTMLDivElement>(null);

  function select(tab: string) {
    const next = new URLSearchParams(params.toString());
    if (tab === tabs[0].id) next.delete(param);
    else next.set(param, tab);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const at = tabs.findIndex((tab) => tab.id === current);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = tabs[(at + step + tabs.length) % tabs.length];
    select(next.id);
    list.current?.querySelector<HTMLElement>(`[data-tab="${next.id}"]`)?.focus();
  }

  return (
    <div>
      <div
        ref={list}
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto border-b border-hairline px-4 sm:mx-0 sm:px-0"
      >
        {tabs.map((tab) => {
          const active = tab.id === current;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              data-tab={tab.id}
              id={`${id}-${tab.id}`}
              aria-selected={active}
              aria-controls={`${id}-panel`}
              tabIndex={active ? 0 : -1}
              onClick={() => select(tab.id)}
              className={`-mb-px shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {tab.label}
              {/* A real space, so it is read as "Payments 3", not "Payments3". */}
              {tab.count !== undefined && " "}
              {tab.count !== undefined && (
                <span
                  className={`ml-0.5 rounded-full px-1.5 py-0.5 text-xs ${
                    active
                      ? "bg-brand-50 text-brand-700"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-${current}`}
        className="pt-4"
      >
        {children}
      </div>
    </div>
  );
}
