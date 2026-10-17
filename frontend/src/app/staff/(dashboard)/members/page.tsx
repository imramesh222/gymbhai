"use client";

import { CalendarPlus, FileSpreadsheet, MessageSquare, UserPlus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState, ListCard, PageHeader } from "@/components/ui/Card";
import { DataTable, type Column, type SortState } from "@/components/ui/DataTable";
import { ExtendEveryone } from "@/components/members/ExtendEveryone";
import { Dialog } from "@/components/ui/Dialog";
import { Menu } from "@/components/ui/Menu";
import { TextArea } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { SmsCounter } from "@/components/ui/SmsCounter";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  errorMessage,
  membersApi,
  type Member,
  type MemberCounts,
  type MemberFilters,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

const PAGE = 50;

const FILTERS: {
  key: keyof MemberCounts;
  label: MessageKey;
  params: MemberFilters;
}[] = [
  { key: "all", label: "members.filter.all", params: {} },
  { key: "active", label: "status.active", params: { status: "active" } },
  { key: "expiring", label: "members.filter.expiring", params: { expiring_within: 7 } },
  { key: "expired", label: "status.expired", params: { status: "expired" } },
  { key: "dues", label: "members.filter.dues", params: { has_dues: true } },
  { key: "frozen", label: "status.frozen", params: { status: "frozen" } },
  {
    key: "not_visiting",
    label: "members.filter.notVisiting",
    params: { not_visiting: true },
  },
  { key: "archived", label: "members.filter.archived", params: { archived: true } },
];

type SortKey = NonNullable<MemberFilters["sort"]>;

function SmsDialog({
  ids,
  onClose,
  onSent,
}: {
  ids: string[];
  onClose: () => void;
  onSent: (queued: number) => void;
}) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  return (
    <Dialog open onClose={onClose} title={t("members.smsTitle", { count: ids.length })}>
      <form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault();
          setPending(true);
          try {
            onSent((await membersApi.smsMany(ids, body)).queued);
          } catch (err) {
            setError(errorMessage(err));
            setPending(false);
          }
        }}
      >
        <TextArea
          label={t("members.smsBody")}
          value={body}
          onChange={setBody}
          required
        />
        <SmsCounter text={body} />
        <p className="text-sm text-slate-600">
          {t("members.smsCost", { count: ids.length })}
        </p>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending || !body.trim()}>
          {t("sms.send")}
        </Button>
      </form>
    </Dialog>
  );
}

/**
 * Members (PLAN.md §7, §16.2 7.6): search, the filters with how many each
 * has, a table on a laptop (cards on a phone) sorted on the server, and one
 * SMS to the members picked.
 */
export default function MembersPage() {
  const { can } = useAuth();
  const { date, display } = useGymCalendar();
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const wanted = params.get("filter");
  const filter = FILTERS.find((f) => f.key === wanted) ?? FILTERS[0];
  const [q, setQ] = useState(params.get("q") ?? "");
  const [query, setQuery] = useState(q);
  const [sort, setSort] = useState<SortState>({ key: "name", direction: "asc" });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [texting, setTexting] = useState(false);
  const [extending, setExtending] = useState(false);

  // Search as they type, but not on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(q);
      setPage(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  const { data, error, reload } = useLoad(
    () =>
      membersApi.list({
        q: query,
        ...filter.params,
        sort: sort.key as SortKey,
        direction: sort.direction,
        limit: PAGE,
        offset: page * PAGE,
      }),
    [query, filter.key, sort.key, sort.direction, page],
  );
  const counts = useLoad(() => membersApi.counts(), []);
  // Another desk added or changed someone, or a member renewed in the app.
  useLive(["member"], () => {
    reload();
    counts.reload();
  });

  function choose(key: string) {
    const next = new URLSearchParams(params.toString());
    if (key === "all") next.delete("filter");
    else next.set("filter", key);
    const text = next.toString();
    router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false });
    setPage(0);
    setSelected(new Set());
  }

  const columns: Column<Member>[] = [
    {
      key: "name",
      header: t("members.col.name"),
      sortable: true,
      cell: (m) => (
        <span className="flex items-center gap-3">
          <Avatar name={m.name} url={m.photo_url} size="size-8" />
          <span className="min-w-0">
            <span className="block truncate font-semibold text-slate-900">
              {m.name}
            </span>
            <span className="block truncate text-xs text-slate-500">
              {m.erased_at ? m.member_code : `${m.member_code} · ${m.phone}`}
            </span>
          </span>
        </span>
      ),
    },
    {
      key: "plan",
      header: t("members.col.plan"),
      cell: (m) => (
        <span className="text-slate-700">{m.current?.plan_name ?? "—"}</span>
      ),
      className: "hidden xl:table-cell",
    },
    {
      key: "status",
      header: t("members.col.status"),
      cell: (m) => (
        <span className="flex flex-col items-start gap-1">
          <StatusBadge status={m.is_archived ? "cancelled" : m.status} />
          <span className="text-xs text-slate-500">
            {m.status === "active" || m.status === "frozen"
              ? t("members.daysLeft", { count: m.days_left })
              : m.valid_until
                ? date(m.valid_until)
                : ""}
          </span>
        </span>
      ),
    },
    {
      key: "dues",
      header: t("members.col.dues"),
      sortable: true,
      align: "right",
      cell: (m) =>
        m.dues > 0 ? (
          <Money paisa={m.dues} className="font-medium text-amber-700" />
        ) : (
          <span className="text-slate-500">—</span>
        ),
    },
    {
      key: "last_visit",
      header: t("members.col.lastVisit"),
      sortable: true,
      align: "right",
      cell: (m) => (
        <span className="text-sm text-slate-600">
          {m.last_visit_at ? formatDateTime(m.last_visit_at, display) : "—"}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={t("members.title")}
        subtitle={data ? t("members.count", { count: data.total }) : undefined}
        actions={
          <>
            {can("members.add") && (
              <Link href="/staff/members/new">
                <Button>
                  <UserPlus className="size-4" aria-hidden />
                  {t("members.add")}
                </Button>
              </Link>
            )}
            <Menu
              items={[
                {
                  label: t("extendAll.title"),
                  icon: CalendarPlus,
                  onSelect: () => setExtending(true),
                  hidden: !can("memberships.extend_all"),
                },
                {
                  label: t("nav.data"),
                  icon: FileSpreadsheet,
                  href: "/staff/data",
                },
              ]}
            />
          </>
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
      <div
        role="group"
        aria-label={t("members.filters")}
        className="no-scrollbar mt-3 flex gap-2 overflow-x-auto pb-1"
      >
        {FILTERS.map((f) => {
          const active = f.key === filter.key;
          const count = counts.data?.[f.key];
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={active}
              onClick={() => choose(f.key)}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                active
                  ? "bg-brand-600 text-white shadow-brand"
                  : "bg-white text-slate-600 shadow-card ring-1 ring-hairline hover:bg-slate-50"
              }`}
            >
              {t(f.label)}
              {count !== undefined && (
                <>
                  {" "}
                  <span className={active ? "text-white/80" : "text-slate-500"}>
                    {count}
                  </span>
                </>
              )}
            </button>
          );
        })}
      </div>

      {selected.size > 0 && (
        <div className="sticky top-16 z-20 mt-3 flex items-center justify-between gap-3 rounded-xl bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lifted lg:top-4">
          <span>{t("members.selected", { count: selected.size })}</span>
          <span className="flex gap-2">
            {can("messages.sms") && (
              <button
                type="button"
                onClick={() => setTexting(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 font-semibold hover:bg-white/20"
              >
                <MessageSquare className="size-4" aria-hidden />
                {t("sms.send")}
              </button>
            )}
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="rounded-lg px-3 py-1.5 text-slate-300 hover:text-white"
            >
              {t("members.clearSelection")}
            </button>
          </span>
        </div>
      )}

      <div className="mt-4">
        {error && <Notice tone="error">{error}</Notice>}
        {!data && !error && <ListSkeleton />}
        {data && (
          <DataTable
            caption={t("members.title")}
            columns={columns}
            rows={data.items}
            rowKey={(m) => m.id}
            href={(m) => `/staff/members/${m.id}`}
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(0);
            }}
            selection={
              can("messages.sms") ? { selected, onChange: setSelected } : undefined
            }
            empty={
              <ListCard>
                <EmptyState
                  title={t("members.none")}
                  action={
                    can("members.add") && filter.key === "all" && !query ? (
                      <Link href="/staff/members/new">
                        <Button>{t("members.add")}</Button>
                      </Link>
                    ) : undefined
                  }
                />
              </ListCard>
            }
            mobile={(m) => (
              <span className="flex items-center gap-3">
                <Avatar name={m.name} url={m.photo_url} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-slate-900">
                    {m.name}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-slate-500">
                    {m.erased_at ? m.member_code : `${m.member_code} · ${m.phone}`}
                    {m.current && ` · ${m.current.plan_name}`}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <StatusBadge status={m.status} />
                  <span className="mt-1 block text-xs text-slate-500">
                    {m.status === "active" || m.status === "frozen"
                      ? t("members.daysLeft", { count: m.days_left })
                      : m.valid_until
                        ? date(m.valid_until)
                        : ""}
                  </span>
                  {m.dues > 0 && (
                    <span className="block text-xs font-medium text-amber-700">
                      {t("members.owes")} <Money paisa={m.dues} />
                    </span>
                  )}
                </span>
              </span>
            )}
          />
        )}
      </div>

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

      {extending && (
        <ExtendEveryone
          onClose={() => {
            setExtending(false);
            reload();
          }}
        />
      )}
      {texting && (
        <SmsDialog
          ids={[...selected]}
          onClose={() => setTexting(false)}
          onSent={(queued) => {
            setTexting(false);
            setSelected(new Set());
            toast.success(t("members.smsSent", { count: queued }));
          }}
        />
      )}
    </div>
  );
}
