"use client";

import { X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { t } from "@/i18n";
import { membersApi, type Member } from "@/lib/api";

export interface Picked {
  id: string;
  name: string;
}

/**
 * Choose one member by name, phone or code: "Referred by" (PLAN.md §16.4,
 * 9.6). Up to five matches as you type; the choice shows as a chip.
 */
export function MemberPicker({
  label,
  value,
  onChange,
  exclude,
}: {
  label: string;
  value: Picked | null;
  onChange: (picked: Picked | null) => void;
  /** Not this member (themselves). */
  exclude?: string;
}) {
  const id = useId();
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Member[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    let gone = false;
    const timer = setTimeout(() => {
      membersApi
        .list({ q, limit: 5 })
        .then((r) => !gone && setFound(r.items.filter((m) => m.id !== exclude)))
        .catch(() => undefined);
    }, 250);
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [q, exclude]);
  const shown = q.trim().length >= 2 ? found : [];

  if (value) {
    return (
      <div>
        <p className="mb-1 text-sm font-medium text-slate-700">{label}</p>
        <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 py-1 pr-1 pl-3 text-sm font-medium text-brand-800 ring-1 ring-brand-200">
          {value.name}
          <button
            type="button"
            onClick={() => onChange(null)}
            className="rounded-full p-1 hover:bg-brand-100"
            aria-label={t("picker.clear", { name: value.name })}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </span>
      </div>
    );
  }
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("picker.placeholder")}
        autoComplete="off"
        className="w-full rounded-xl bg-white px-3 py-2.5 text-base ring-1 ring-hairline outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500"
      />
      {shown.length > 0 && (
        <ul className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-xl bg-white shadow-raised ring-1 ring-hairline">
          {shown.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                onClick={() => {
                  onChange({ id: m.id, name: m.name });
                  setQ("");
                }}
                className="flex w-full justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="truncate font-medium">{m.name}</span>
                <span className="shrink-0 text-slate-500">{m.member_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
