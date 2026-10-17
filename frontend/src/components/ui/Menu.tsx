"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { t } from "@/i18n";

export interface MenuItem {
  label: string;
  onSelect?: () => void;
  href?: string;
  icon?: React.ComponentType<{ className?: string }>;
  /** Red, for actions that remove or can't be undone. */
  danger?: boolean;
  hidden?: boolean;
}

/**
 * "More ▾": the actions a screen needs now and then, kept out of the way of
 * the ones used all day. Keyboard: arrows move, Enter picks, Escape closes.
 */
export function Menu({
  items,
  label = t("common.more"),
  align = "right",
}: {
  items: MenuItem[];
  label?: string;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const shown = items.filter((item) => !item.hidden);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    // The first item takes focus, as in any menu.
    root.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  if (shown.length === 0) return null;

  function onKeyDown(event: React.KeyboardEvent) {
    const entries = Array.from(
      root.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? [],
    );
    const at = entries.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") {
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      entries[(at + 1) % entries.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      entries[(at - 1 + entries.length) % entries.length]?.focus();
    }
  }

  const itemClass = (danger?: boolean) =>
    `flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm outline-none transition focus:bg-slate-100 hover:bg-slate-100 ${
      danger ? "text-red-700" : "text-slate-700"
    }`;

  return (
    <div ref={root} className="relative" onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 shadow-card ring-1 ring-hairline transition hover:bg-slate-50"
      >
        {label}
        <ChevronDown className="size-4 text-slate-500" aria-hidden />
      </button>
      {open && (
        <div
          id={id}
          role="menu"
          className={`absolute z-30 mt-1.5 min-w-52 overflow-hidden rounded-xl bg-surface py-1 shadow-lifted ring-1 ring-hairline ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {shown.map((item) => {
            const Icon = item.icon;
            const body = (
              <>
                {Icon && <Icon className="size-4 shrink-0 opacity-70" />}
                {item.label}
              </>
            );
            return item.href ? (
              <Link
                key={item.label}
                href={item.href}
                role="menuitem"
                tabIndex={-1}
                className={itemClass(item.danger)}
                onClick={() => setOpen(false)}
              >
                {body}
              </Link>
            ) : (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                tabIndex={-1}
                className={itemClass(item.danger)}
                onClick={() => {
                  setOpen(false);
                  item.onSelect?.();
                }}
              >
                {body}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
