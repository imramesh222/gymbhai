"use client";

import { CalendarCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { RecordSession } from "@/components/training/RecordSession";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs, useTab, type Tab } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { ptApi, type PtPackage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { mayRecord, sessionsLine } from "@/lib/training";
import { useLoad } from "@/lib/useLoad";

/**
 * Personal training (PLAN.md §18.3): a trainer's own clients, with Record
 * session one tap away, and everyone's, by trainer, for staff who sell it.
 * Only what is still to train: upcoming and under way.
 */
export default function TrainingPage() {
  const { can } = useAuth();
  const trains = can("pt.train");
  const sells = can("pt.sell");
  const tabs: Tab[] = [
    ...(trains ? [{ id: "mine", label: t("pt.tab.mine") }] : []),
    ...(sells ? [{ id: "all", label: t("pt.tab.all") }] : []),
  ];
  const tab = useTab(tabs);
  const [trainerId, setTrainerId] = useState("");

  const mine = useLoad(
    () => (trains ? ptApi.clients() : Promise.resolve(null)),
    [trains],
  );
  const all = useLoad(
    () => (sells ? ptApi.all(trainerId || undefined) : Promise.resolve(null)),
    [sells, trainerId],
  );
  const trainers = useLoad(
    () => (sells ? ptApi.trainers() : Promise.resolve([])),
    [sells],
  );
  useLive(["pt"], () => {
    mine.reload();
    all.reload();
  });

  if (tabs.length === 0)
    return <Notice tone="error">{t("errors.permission_denied")}</Notice>;
  const shown = tab === "all" ? all : mine;
  return (
    <div className="space-y-4">
      <PageHeader title={t("pt.title")} />
      <Tabs tabs={tabs} label={t("pt.title")}>
        <div className="space-y-4">
          {tab === "all" && (trainers.data?.length ?? 0) > 1 && (
            <div className="max-w-xs">
              <Select
                label={t("pt.trainer")}
                value={trainerId}
                onChange={setTrainerId}
                options={[
                  { value: "", label: t("pt.allTrainers") },
                  ...(trainers.data ?? []).map((tr) => ({
                    value: tr.id,
                    label: tr.name,
                  })),
                ]}
              />
            </div>
          )}
          {shown.error && <Notice tone="error">{shown.error}</Notice>}
          {!shown.data ? (
            !shown.error && <ListSkeleton rows={3} />
          ) : shown.data.length === 0 ? (
            <Card>
              <EmptyState title={tab === "all" ? t("pt.noneAll") : t("pt.noClients")} />
            </Card>
          ) : tab === "all" && !trainerId ? (
            byTrainer(shown.data).map(([name, packages]) => (
              <Card key={name} title={name}>
                <Clients packages={packages} onChanged={shown.reload} />
              </Card>
            ))
          ) : (
            <Card>
              <Clients packages={shown.data} onChanged={shown.reload} />
            </Card>
          )}
        </div>
      </Tabs>
    </div>
  );
}

function byTrainer(packages: PtPackage[]): [string, PtPackage[]][] {
  const groups = new Map<string, PtPackage[]>();
  for (const pkg of packages) {
    const name = pkg.trainer_name ?? "—";
    groups.set(name, [...(groups.get(name) ?? []), pkg]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function Clients({
  packages,
  onChanged,
}: {
  packages: PtPackage[];
  onChanged: () => void;
}) {
  const { can, me } = useAuth();
  const { date } = useGymCalendar();
  const toast = useToast();
  const [recording, setRecording] = useState<PtPackage | null>(null);
  return (
    <>
      <ul className="divide-y divide-hairline">
        {packages.map((pkg) => (
          <li
            key={pkg.id}
            className="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <div className="min-w-0">
              <p className="font-medium text-slate-900">
                {can("members.view") ? (
                  <Link
                    href={`/staff/members/${pkg.member_id}?tab=training`}
                    className="hover:underline"
                  >
                    {pkg.member_name}
                  </Link>
                ) : (
                  pkg.member_name
                )}{" "}
                <span className="text-xs font-normal text-slate-500">
                  {pkg.member_code}
                </span>
              </p>
              <p className="text-sm text-slate-600">
                {pkg.plan_name} · {sessionsLine(pkg)}
              </p>
              <p className="text-xs text-slate-500">
                {pkg.status === "upcoming"
                  ? t("pt.startsOn", { date: date(pkg.start_date) })
                  : t("pt.endsOn", { date: date(pkg.end_date) })}{" "}
                ·{" "}
                {pkg.last_session_on
                  ? t("pt.lastSession", { date: date(pkg.last_session_on) })
                  : t("pt.noSessionYet")}
                {pkg.dues > 0 && (
                  <span className="font-medium text-amber-700">
                    {" "}
                    · {t("members.owes")} <Money paisa={pkg.dues} />
                  </span>
                )}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {pkg.status === "upcoming" && <StatusBadge status={pkg.status} />}
              {mayRecord(pkg, me?.staff.id, can) && (
                <Button size="sm" onClick={() => setRecording(pkg)}>
                  <CalendarCheck className="size-3.5" aria-hidden />
                  {t("pt.record")}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {recording && (
        <RecordSession
          pkg={recording}
          onClose={() => setRecording(null)}
          onRecorded={() => {
            setRecording(null);
            toast.success(t("pt.recorded"));
            onChanged();
          }}
        />
      )}
    </>
  );
}
