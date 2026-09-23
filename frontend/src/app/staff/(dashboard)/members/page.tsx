"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { EmptyState, ListCard, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { Avatar } from "@/components/ui/Avatar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t, type MessageKey } from "@/i18n";
import { membersApi, type MemberStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

const FILTERS: { key: string; label: MessageKey; params: Record<string, unknown> }[] = [
  { key: "all", label: "members.filter.all", params: {} },
  { key: "active", label: "status.active", params: { status: "active" } },
  { key: "expiring", label: "members.filter.expiring", params: { expiring_within: 7 } },
  { key: "expired", label: "status.expired", params: { status: "expired" } },
  { key: "dues", label: "members.filter.dues", params: { has_dues: true } },
  { key: "frozen", label: "status.frozen", params: { status: "frozen" } },
  { key: "archived", label: "members.filter.archived", params: { archived: true } },
];

const PAGE = 50;

export default function MembersPage() {
  const { can } = useAuth();
  const { date } = useGymCalendar();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);

  // Search as they type, but not on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(q);
      setPage(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  const params = FILTERS.find((f) => f.key === filter)?.params ?? {};
  const { data, error, loading } = useLoad(
    () =>
      membersApi.list({
        q: query,
        ...(params as { status?: MemberStatus }),
        limit: PAGE,
        offset: page * PAGE,
      }),
    [query, filter, page],
  );

  return (
    <div>
      <PageHeader
        title={t("members.title")}
        subtitle={data ? t("members.count", { count: data.total }) : undefined}
        actions={
          can("members.add") && (
            <Link href="/staff/members/new">
              <Button>{t("members.add")}</Button>
            </Link>
          )
        }
      />
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("members.search")}
        aria-label={t("members.search")}
        className="w-full rounded-xl bg-white px-4 py-3 text-base shadow-card ring-1 ring-hairline outline-none transition placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500"
      />
      <div className="no-scrollbar mt-3 flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => {
              setFilter(f.key);
              setPage(0);
            }}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              filter === f.key
                ? "bg-brand-600 text-white shadow-brand"
                : "bg-white text-slate-600 shadow-card ring-1 ring-hairline hover:bg-slate-50"
            }`}
          >
            {t(f.label)}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {loading && !data && (
        <p className="mt-6 text-sm text-slate-500">{t("common.loading")}</p>
      )}
      {data && data.items.length === 0 && (
        <div className="mt-4">
          <ListCard>
            <EmptyState title={t("members.none")} />
          </ListCard>
        </div>
      )}

      {data && data.items.length > 0 && (
        <ul className="mt-4 divide-y divide-hairline overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-hairline">
          {data.items.map((m) => (
            <li key={m.id}>
              <Link
                href={`/staff/members/${m.id}`}
                className="flex items-center gap-3 px-4 py-3 transition hover:bg-slate-50"
              >
                <Avatar name={m.name} url={m.photo_url} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-slate-900">{m.name}</p>
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    {m.member_code} · {m.phone}
                    {m.current && ` · ${m.current.plan_name}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <StatusBadge status={m.status} />
                  <p className="mt-1 text-xs text-slate-500">
                    {m.status === "active" || m.status === "frozen"
                      ? t("members.daysLeft", { count: m.days_left })
                      : m.valid_until
                        ? date(m.valid_until)
                        : ""}
                  </p>
                  {m.dues > 0 && (
                    <p className="text-xs font-medium text-amber-700">
                      {t("members.owes")} <Money paisa={m.dues} />
                    </p>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between">
          <Button
            variant="secondary"
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
          >
            {t("common.previous")}
          </Button>
          <span className="text-sm text-slate-600">
            {t("common.pageOf", {
              page: page + 1,
              pages: Math.ceil(data.total / PAGE),
            })}
          </span>
          <Button
            variant="secondary"
            disabled={(page + 1) * PAGE >= data.total}
            onClick={() => setPage(page + 1)}
          >
            {t("common.next")}
          </Button>
        </div>
      )}
    </div>
  );
}
