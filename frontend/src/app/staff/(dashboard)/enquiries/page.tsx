"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { AddLead } from "@/components/leads/AddLead";
import { LeadDialog } from "@/components/leads/LeadDialog";
import { LeadsReport } from "@/components/leads/LeadsReport";
import { EmptyState, PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { Tabs, useTab, type Tab } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  LEAD_STATUSES,
  leadsApi,
  plansApi,
  type Lead,
  type LeadStatus,
} from "@/lib/api";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

function LeadCard({ lead, onOpen }: { lead: Lead; onOpen: () => void }) {
  const { date } = useGymCalendar();
  const overdue =
    lead.follow_up_on !== null &&
    lead.follow_up_on <= todayInNepal() &&
    ["new", "contacted", "trial"].includes(lead.status);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="block w-full rounded-xl bg-white p-3 text-left text-sm shadow-card ring-1 ring-hairline transition hover:ring-brand-300"
    >
      <p className="truncate font-semibold text-slate-900">{lead.name}</p>
      <p className="truncate text-xs text-slate-500">
        {t(`leads.source.${lead.source}` as MessageKey)}
        {lead.plan_name && ` · ${lead.plan_name}`}
      </p>
      {lead.follow_up_on && ["new", "contacted", "trial"].includes(lead.status) && (
        <p
          className={`mt-1 text-xs font-medium ${overdue ? "text-amber-700" : "text-slate-500"}`}
        >
          {t("leads.callOn", { date: date(lead.follow_up_on) })}
        </p>
      )}
      {lead.assigned_name && (
        <p className="mt-0.5 text-xs text-slate-500">{lead.assigned_name}</p>
      )}
    </button>
  );
}

/** Enquiries as a board by status, or a list, and where they come from (9.1). */
export default function EnquiriesPage() {
  const toast = useToast();
  const { data, error, reload } = useLoad(() => leadsApi.list(), []);
  const plans = useLoad(() => plansApi.list(), []);
  useLive(["lead", "member"], reload);
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const tabs: Tab[] = [
    { id: "board", label: t("leads.tab.board") },
    { id: "list", label: t("leads.tab.list") },
    { id: "report", label: t("leads.tab.report") },
  ];
  const tab = useTab(tabs);
  const open = data?.find((l) => l.id === openId) ?? null;
  const by = (status: LeadStatus) => (data ?? []).filter((l) => l.status === status);

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("leads.title")}
        subtitle={t("leads.subtitle")}
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus className="size-4" aria-hidden />
            {t("leads.add")}
          </Button>
        }
      />
      <Tabs tabs={tabs} label={t("leads.title")}>
        {tab === "report" ? (
          <LeadsReport />
        ) : !data ? (
          !error && <PageSkeleton label={t("common.loading")} />
        ) : data.length === 0 ? (
          <EmptyState title={t("leads.none")} hint={t("leads.noneHint")} />
        ) : tab === "board" ? (
          <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 lg:mx-0 lg:grid lg:grid-cols-5 lg:overflow-visible lg:px-0">
            {LEAD_STATUSES.map((status) => (
              <section
                key={status}
                aria-label={t(`leads.status.${status}` as MessageKey)}
                className="w-64 shrink-0 snap-start space-y-2 rounded-2xl bg-slate-100/70 p-2 lg:w-auto"
              >
                <h2 className="flex justify-between px-1 text-xs font-semibold tracking-wide text-slate-600 uppercase">
                  {t(`leads.status.${status}` as MessageKey)}
                  <span>{by(status).length}</span>
                </h2>
                {by(status).map((lead) => (
                  <LeadCard
                    key={lead.id}
                    lead={lead}
                    onOpen={() => setOpenId(lead.id)}
                  />
                ))}
              </section>
            ))}
          </div>
        ) : (
          <ul className="space-y-2">
            {data.map((lead) => (
              <li key={lead.id} className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <LeadCard lead={lead} onOpen={() => setOpenId(lead.id)} />
                </div>
                <span className="w-24 shrink-0 text-right text-xs font-semibold text-slate-600">
                  {t(`leads.status.${lead.status}` as MessageKey)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Tabs>
      {adding && (
        <AddLead
          plans={plans.data ?? []}
          onClose={() => setAdding(false)}
          onAdded={(lead) => {
            setAdding(false);
            toast.success(t("leads.added", { name: lead.name }));
            reload();
          }}
        />
      )}
      {open && (
        <LeadDialog
          key={open.id}
          lead={open}
          onClose={() => setOpenId(null)}
          onChanged={() => reload()}
        />
      )}
    </div>
  );
}
