"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { ClassDialog, dayOf, timeOf } from "@/components/classes/ClassDialog";
import { ColorDot } from "@/components/classes/ClassSettings";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/inputs";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { Tabs, useTab, type Tab } from "@/components/ui/Tabs";
import { t } from "@/i18n";
import { dayName } from "@shared/accessHours";
import { inNepal } from "@shared/door/offline";
import { branchesApi, classesApi, type GymClass } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { addDays, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

/**
 * Desk → Classes (PLAN.md §19.4): the week's classes by day, with places
 * booked and the waitlist; open one for its roster. An instructor's own
 * classes under My classes.
 */
export default function ClassesPage() {
  const { can } = useAuth();
  const { date } = useGymCalendar();
  const runs = can("classes.book") || can("classes.manage");
  const tabs: Tab[] = [
    ...(runs ? [{ id: "all", label: t("classes.tab.all") }] : []),
    ...(can("classes.teach") ? [{ id: "mine", label: t("classes.tab.mine") }] : []),
  ];
  const tab = useTab(tabs);
  const today = todayInNepal();
  const [from, setFrom] = useState(today);
  // "all": the Select keeps "" for its own "Choose…".
  const [branchId, setBranchId] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const branches = useLoad(() => branchesApi.list(), []);
  const week = useLoad(
    () =>
      tab === "mine"
        ? classesApi.mine(from)
        : classesApi.week(from, branchId === "all" ? undefined : branchId),
    [tab, from, branchId],
  );
  useLive(["class"], week.reload);

  if (tabs.length === 0)
    return <Notice tone="error">{t("errors.permission_denied")}</Notice>;
  const days = byDay(week.data ?? []);
  return (
    <div className="space-y-4">
      <PageHeader title={t("classes.title")} />
      <Tabs tabs={tabs} label={t("classes.title")}>
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFrom(addDays(from, -7))}
            >
              ‹ {t("classes.prevWeek")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFrom(today)}
              disabled={from === today}
            >
              {t("classes.thisWeek")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFrom(addDays(from, 7))}
            >
              {t("classes.nextWeek")} ›
            </Button>
            <span className="text-sm text-slate-600">
              {t("classes.weekOf", { date: date(from) })}
            </span>
            {tab !== "mine" && (branches.data?.length ?? 0) > 1 && (
              <div className="ml-auto w-48">
                <Select
                  label={t("sale.branch")}
                  value={branchId}
                  onChange={setBranchId}
                  options={[
                    { value: "all", label: t("classes.allBranches") },
                    ...(branches.data ?? []).map((b) => ({
                      value: b.id,
                      label: b.name,
                    })),
                  ]}
                />
              </div>
            )}
          </div>
          {week.error && <Notice tone="error">{week.error}</Notice>}
          {!week.data ? (
            !week.error && <ListSkeleton rows={4} />
          ) : days.length === 0 ? (
            <Card>
              <EmptyState title={t("classes.none")} />
            </Card>
          ) : (
            days.map(([day, classes]) => (
              <Card
                key={day}
                title={`${dayName(inNepal(Date.parse(`${day}T06:00:00+05:45`)).weekday)}, ${date(day)}`}
              >
                <ul className="divide-y divide-hairline">
                  {classes.map((c) => (
                    <ClassRow key={c.id} gymClass={c} onOpen={() => setOpen(c.id)} />
                  ))}
                </ul>
              </Card>
            ))
          )}
        </div>
      </Tabs>
      {open && (
        <ClassDialog
          classId={open}
          onClose={() => setOpen(null)}
          onChanged={week.reload}
        />
      )}
    </div>
  );
}

function byDay(classes: GymClass[]): [string, GymClass[]][] {
  const days = new Map<string, GymClass[]>();
  for (const c of classes) {
    const day = dayOf(c.starts_at);
    days.set(day, [...(days.get(day) ?? []), c]);
  }
  return [...days.entries()];
}

function ClassRow({ gymClass: c, onOpen }: { gymClass: GymClass; onOpen: () => void }) {
  const full = c.booked >= c.places;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:bg-slate-50"
      >
        <span className="w-12 shrink-0 font-semibold tabular-nums">
          {timeOf(c.starts_at)}
        </span>
        <ColorDot color={c.color} />
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate font-medium ${c.cancelled_at ? "text-slate-400 line-through" : ""}`}
          >
            {c.type_name}
          </span>
          {c.instructor_name && (
            <span className="block truncate text-xs text-slate-500">
              {c.instructor_name}
            </span>
          )}
        </span>
        <span className="shrink-0 text-right text-xs">
          {c.cancelled_at ? (
            <span className="font-semibold text-red-700">{t("classes.cancelled")}</span>
          ) : (
            <>
              <span
                className={`block font-semibold ${full ? "text-amber-700" : "text-slate-700"}`}
              >
                {full
                  ? t("classes.full")
                  : t("classes.booked", { booked: c.booked, places: c.places })}
              </span>
              {c.waiting > 0 && (
                <span className="block text-slate-500">
                  {t("classes.waiting", { count: c.waiting })}
                </span>
              )}
            </>
          )}
        </span>
      </button>
    </li>
  );
}
