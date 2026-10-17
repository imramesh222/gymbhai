"use client";

import { ScanLine, Search, UserPlus, Wallet, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Money } from "@/components/ui/Money";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { branchesApi, doorApi, errorMessage, membersApi, type Member } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Action {
  id: string;
  label: MessageKey;
  href: string;
  icon: LucideIcon;
  anyOf: string[];
}

const ACTIONS: Action[] = [
  {
    id: "add",
    label: "palette.addMember",
    href: "/staff/members/new",
    icon: UserPlus,
    anyOf: ["members.add"],
  },
  {
    id: "scan",
    label: "palette.scan",
    href: "/staff/door",
    icon: ScanLine,
    anyOf: ["door.check_in"],
  },
  {
    id: "payments",
    label: "palette.payments",
    href: "/staff/payments",
    icon: Wallet,
    anyOf: ["reports.money"],
  },
];

/** Opens on Ctrl/⌘+K, or / when nothing is being typed. */
export function usePaletteShortcut(open: () => void) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.isContentEditable ||
        /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName ?? "");
      if (
        (event.key === "k" && (event.metaKey || event.ctrlKey)) ||
        (event.key === "/" && !typing)
      ) {
        event.preventDefault();
        open();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
}

/**
 * Search from any screen (PLAN.md §16.2, 7.3): members by name, phone or
 * code, with what the desk does next — open, renew, check in — and the
 * dashboard's everyday actions.
 */
export function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const { can } = useAuth();
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  // Answers remember the search they answer, so a slow one never shows late.
  const [found, setFound] = useState<{ q: string; members: Member[] }>({
    q: "",
    members: [],
  });
  const [active, setActive] = useState(0);
  const text = q.trim();
  const searchable = text.length >= 2 && can("members.view");
  const members = searchable && found.q === text ? found.members : [];
  const searching = searchable && found.q !== text;
  const [singleBranch, setSingleBranch] = useState<string | null>(null);

  const actions = useMemo(
    () =>
      ACTIONS.filter(
        (action) =>
          action.anyOf.some(can) &&
          (!q || t(action.label).toLowerCase().includes(q.trim().toLowerCase())),
      ),
    [can, q],
  );
  const total = actions.length + members.length;

  useEffect(() => {
    input.current?.focus();
    // Checking in from here needs a branch: only when there is just one.
    branchesApi
      .list()
      .then((branches) =>
        setSingleBranch(branches.length === 1 ? branches[0].id : null),
      )
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!searchable) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      membersApi
        .list({ q: text, limit: 8 })
        .then((page) => !cancelled && setFound({ q: text, members: page.items }))
        .catch(() => !cancelled && setFound({ q: text, members: [] }));
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [text, searchable]);

  const go = useCallback(
    (href: string) => {
      onClose();
      router.push(href);
    },
    [onClose, router],
  );

  async function checkIn(member: Member) {
    if (!singleBranch) return go("/staff/door");
    try {
      const result = await doorApi.manual({
        member_id: member.id,
        branch_id: singleBranch,
      });
      const outcome = t(`door.result.${result.result}` as MessageKey);
      if (result.let_in) toast.success(`${member.name} — ${outcome}`);
      else toast.error(`${member.name} — ${outcome}`);
      onClose();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  function choose(index: number) {
    if (index < actions.length) return go(actions[index].href);
    const member = members[index - actions.length];
    if (member) go(`/staff/members/${member.id}`);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") onClose();
    else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((at) => (total ? (at + 1) % total : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((at) => (total ? (at - 1 + total) % total : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(active);
    }
  }

  const optionId = (index: number) => `${listId}-${index}`;
  const row = (index: number) =>
    `flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left ${
      index === active ? "bg-brand-50" : "hover:bg-slate-50"
    }`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 px-3 pt-[10vh] backdrop-blur-[2px] print:hidden"
      onPointerDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("nav.search")}
        className="w-full max-w-xl overflow-hidden rounded-2xl bg-surface shadow-lifted ring-1 ring-hairline"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-3 border-b border-hairline px-4">
          <Search className="size-5 shrink-0 text-slate-500" aria-hidden />
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={total ? optionId(active) : undefined}
            aria-label={t("palette.label")}
            placeholder={t("palette.placeholder")}
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setActive(0);
            }}
            className="h-14 w-full bg-transparent text-base text-slate-900 outline-none placeholder:text-slate-400"
          />
          <kbd className="hidden rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 sm:block">
            Esc
          </kbd>
        </div>
        <div
          id={listId}
          role="listbox"
          aria-label={t("palette.results")}
          className="max-h-[60vh] overflow-y-auto p-2"
        >
          {actions.map((action, index) => {
            const Icon = action.icon;
            return (
              <button
                key={action.id}
                id={optionId(index)}
                type="button"
                role="option"
                aria-selected={index === active}
                onPointerEnter={() => setActive(index)}
                onClick={() => go(action.href)}
                className={row(index)}
              >
                <span className="flex size-9 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="text-sm font-medium text-slate-800">
                  {t(action.label)}
                </span>
              </button>
            );
          })}
          {members.map((member, offset) => {
            const index = actions.length + offset;
            return (
              <div
                key={member.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                onPointerEnter={() => setActive(index)}
                className={row(index)}
              >
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => go(`/staff/members/${member.id}`)}
                  className="flex min-w-0 flex-1 items-center gap-3 text-left"
                >
                  <Avatar name={member.name} url={member.photo_url} size="size-9" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-slate-900">
                      {member.name}
                    </span>
                    <span className="block truncate text-xs text-slate-500">
                      {member.member_code} · {member.phone}
                      {member.dues > 0 && (
                        <>
                          {" · "}
                          <span className="text-amber-700">
                            {t("members.owes")} <Money paisa={member.dues} />
                          </span>
                        </>
                      )}
                    </span>
                  </span>
                </button>
                <StatusBadge status={member.status} />
                <span className="hidden gap-1 sm:flex">
                  {can("memberships.sell") && (
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => go(`/staff/members/${member.id}/renew`)}
                      className="rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-100"
                    >
                      {member.status === "none" ? t("member.sell") : t("member.renew")}
                    </button>
                  )}
                  {can("door.check_in") && (
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => void checkIn(member)}
                      className="rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-100"
                    >
                      {t("palette.checkIn")}
                    </button>
                  )}
                </span>
              </div>
            );
          })}
          {searchable && !searching && members.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              {t("palette.nothing", { q: text })}
            </p>
          )}
          {text.length < 2 && (
            <p className="px-3 pt-2 pb-1 text-xs text-slate-500">{t("palette.hint")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
