"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { t } from "@/i18n";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  /** The page sorts (usually the API does): the table only asks. */
  sortable?: boolean;
  align?: "left" | "right";
  className?: string;
}

export interface SortState {
  key: string;
  direction: "asc" | "desc";
}

interface Selection {
  selected: ReadonlySet<string>;
  onChange: (selected: Set<string>) => void;
}

function SelectAll<T>({
  rows,
  rowKey,
  selection,
}: {
  rows: T[];
  rowKey: (row: T) => string;
  selection: Selection;
}) {
  const box = useRef<HTMLInputElement>(null);
  const ids = rows.map(rowKey);
  const chosen = ids.filter((id) => selection.selected.has(id)).length;
  useEffect(() => {
    if (box.current) box.current.indeterminate = chosen > 0 && chosen < ids.length;
  }, [chosen, ids.length]);
  return (
    <input
      ref={box}
      type="checkbox"
      aria-label={t("table.selectAll")}
      checked={ids.length > 0 && chosen === ids.length}
      onChange={(event) => selection.onChange(new Set(event.target.checked ? ids : []))}
      className="size-4 accent-brand-600"
    />
  );
}

/**
 * A list as a table on a laptop and as cards on a phone (`mobile` draws one
 * card). Rows open `href` when clicked; the first column carries the real
 * link, so keyboards and "open in new tab" work too.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  href,
  sort,
  onSortChange,
  selection,
  mobile,
  empty,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  href?: (row: T) => string;
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  selection?: Selection;
  mobile: (row: T) => React.ReactNode;
  empty?: React.ReactNode;
}) {
  const router = useRouter();
  if (rows.length === 0 && empty) return <>{empty}</>;

  function toggle(id: string, on: boolean) {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (on) next.add(id);
    else next.delete(id);
    selection.onChange(next);
  }

  function header(column: Column<T>) {
    if (!column.sortable || !onSortChange) return column.header;
    const active = sort?.key === column.key;
    const Icon = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
    return (
      <button
        type="button"
        onClick={() =>
          onSortChange({
            key: column.key,
            direction: active && sort.direction === "asc" ? "desc" : "asc",
          })
        }
        className={`inline-flex items-center gap-1 transition hover:text-slate-900 ${
          active ? "text-slate-900" : ""
        }`}
      >
        {column.header}
        <Icon className={`size-3.5 ${active ? "" : "opacity-40"}`} aria-hidden />
      </button>
    );
  }

  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-hairline md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 z-10 bg-slate-50/95 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase backdrop-blur">
            <tr>
              {selection && (
                <th scope="col" className="w-10 px-4 py-3">
                  <SelectAll rows={rows} rowKey={rowKey} selection={selection} />
                </th>
              )}
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={
                    sort?.key === column.key
                      ? sort.direction === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                  className={`px-4 py-3 ${column.align === "right" ? "text-right" : ""} ${
                    column.className ?? ""
                  }`}
                >
                  {header(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {rows.map((row) => {
              const id = rowKey(row);
              const link = href?.(row);
              return (
                <tr
                  key={id}
                  onClick={(event) => {
                    // Clicks on the link, a checkbox or a button do their own thing.
                    if ((event.target as HTMLElement).closest("a,button,input")) return;
                    if (link) router.push(link);
                  }}
                  className={`transition ${link ? "cursor-pointer hover:bg-slate-50/80" : ""} ${
                    selection?.selected.has(id) ? "bg-brand-50/60" : ""
                  }`}
                >
                  {selection && (
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={t("table.selectRow")}
                        checked={selection.selected.has(id)}
                        onChange={(event) => toggle(id, event.target.checked)}
                        className="size-4 accent-brand-600"
                      />
                    </td>
                  )}
                  {columns.map((column, index) => (
                    <td
                      key={column.key}
                      className={`px-4 py-3 ${column.align === "right" ? "text-right" : ""} ${
                        column.className ?? ""
                      }`}
                    >
                      {index === 0 && link ? (
                        <Link href={link} className="block outline-offset-4">
                          {column.cell(row)}
                        </Link>
                      ) : (
                        column.cell(row)
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-hairline overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-hairline md:hidden">
        {rows.map((row) => {
          const id = rowKey(row);
          const link = href?.(row);
          return (
            <li key={id} className="flex items-center gap-3 px-4">
              {selection && (
                <input
                  type="checkbox"
                  aria-label={t("table.selectRow")}
                  checked={selection.selected.has(id)}
                  onChange={(event) => toggle(id, event.target.checked)}
                  className="size-4 shrink-0 accent-brand-600"
                />
              )}
              {link ? (
                <Link href={link} className="block min-w-0 flex-1 py-3">
                  {mobile(row)}
                </Link>
              ) : (
                <div className="min-w-0 flex-1 py-3">{mobile(row)}</div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
