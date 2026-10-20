"use client";

import { Phone, UserCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { WhatsAppLink } from "@/components/member/WhatsApp";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { Row } from "@/components/ui/Card";
import { DateInput, TextArea } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, leadsApi, type Lead } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";

/**
 * One enquiry and what to do next (PLAN.md §16.4, 9.1, 9.2): call them, note
 * the call, a trial visit today, the next follow-up, lost (and why), or
 * Convert to a member.
 */
export function LeadDialog({
  lead,
  onClose,
  onChanged,
}: {
  lead: Lead;
  onClose: () => void;
  onChanged: (lead: Lead) => void;
}) {
  // The dialog stays open while the enquiry changes; only its fields start
  // again from each saved change. Opening a new <dialog> for every change
  // left a gap in which Escape closed the old one and the new one opened.
  return (
    <Dialog open onClose={onClose} title={lead.name}>
      <LeadDetails key={lead.updated_at} lead={lead} onChanged={onChanged} />
    </Dialog>
  );
}

function LeadDetails({
  lead,
  onChanged,
}: {
  lead: Lead;
  onChanged: (lead: Lead) => void;
}) {
  const { me, can } = useAuth();
  const { date, display } = useGymCalendar();
  const toast = useToast();
  const [followUp, setFollowUp] = useState(lead.follow_up_on ?? "");
  const [notes, setNotes] = useState(lead.notes ?? "");
  const [losing, setLosing] = useState(false);
  const [lostReason, setLostReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const open = lead.status !== "joined" && lead.status !== "lost";

  async function run(action: () => Promise<Lead>, message: string) {
    setError(null);
    try {
      const updated = await action();
      toast.success(message);
      onChanged(updated);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <dl>
        <Row label={t("leads.status")}>
          {t(`leads.status.${lead.status}` as MessageKey)}
          {lead.lost_reason && ` — ${lead.lost_reason}`}
        </Row>
        {lead.phone && (
          <Row label={t("member.phone")}>
            <span className="inline-flex flex-wrap items-center gap-3">
              <a
                href={`tel:${lead.phone}`}
                className="inline-flex items-center gap-1 font-medium text-brand-700"
              >
                <Phone className="size-3.5" aria-hidden />
                {lead.phone}
              </a>
              <WhatsAppLink
                phone={lead.phone}
                className="inline-flex items-center gap-1 font-medium text-brand-700"
                iconClassName="size-3.5"
              />
            </span>
          </Row>
        )}
        {lead.email && <Row label={t("member.email")}>{lead.email}</Row>}
        <Row label={t("leads.source")}>
          {t(`leads.source.${lead.source}` as MessageKey)}
          {lead.referred_by_name && ` (${lead.referred_by_name})`}
        </Row>
        {lead.plan_name && <Row label={t("leads.plan")}>{lead.plan_name}</Row>}
        {lead.trial_on && <Row label={t("leads.trialOn")}>{date(lead.trial_on)}</Row>}
        <Row label={t("leads.assigned")}>{lead.assigned_name ?? "—"}</Row>
        <Row label={t("leads.asked")}>{date(lead.created_at.slice(0, 10))}</Row>
      </dl>

      {lead.member_id && (
        <Link
          href={`/staff/members/${lead.member_id}`}
          className="block text-sm font-semibold text-brand-700 hover:underline"
        >
          {t("leads.seeMember")}
        </Link>
      )}

      {open && (
        <>
          <div className="flex flex-wrap gap-2">
            {can("members.add") && (
              <Link
                href={`/staff/members/new?lead=${lead.id}`}
                className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-brand hover:bg-brand-700"
              >
                <UserCheck className="size-4" aria-hidden />
                {t("leads.convert")}
              </Link>
            )}
            {lead.status === "new" && (
              <Button
                variant="secondary"
                onClick={() =>
                  void run(
                    () => leadsApi.update(lead.id, { status: "contacted" }),
                    t("leads.markedContacted"),
                  )
                }
              >
                {t("leads.contacted")}
              </Button>
            )}
            {lead.status !== "trial" && (
              <Button
                variant="secondary"
                onClick={() =>
                  void run(() => leadsApi.trial(lead.id), t("leads.trialSaved"))
                }
              >
                {t("leads.trialToday")}
              </Button>
            )}
            {me && lead.assigned_to !== me.staff.id && (
              <Button
                variant="ghost"
                onClick={() =>
                  void run(
                    () => leadsApi.update(lead.id, { assigned_to: me.staff.id }),
                    t("leads.taken"),
                  )
                }
              >
                {t("leads.takeIt")}
              </Button>
            )}
          </div>

          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void run(
                () =>
                  leadsApi.update(lead.id, {
                    follow_up_on: followUp || null,
                    notes: notes || null,
                  }),
                t("common.saved"),
              );
            }}
          >
            <DateInput
              label={t("leads.followUpOn")}
              value={followUp}
              onChange={setFollowUp}
              display={display}
            />
            <TextArea
              label={t("leads.notes")}
              value={notes}
              onChange={setNotes}
              rows={3}
            />
            <Button type="submit" variant="secondary">
              {t("common.save")}
            </Button>
          </form>

          {losing ? (
            <form
              className="space-y-2 rounded-xl bg-slate-50 p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  () =>
                    leadsApi.update(lead.id, {
                      status: "lost",
                      lost_reason: lostReason,
                    }),
                  t("leads.markedLost"),
                );
              }}
            >
              <Field
                label={t("leads.lostReason")}
                value={lostReason}
                onChange={setLostReason}
                required
              />
              <Button type="submit" variant="danger">
                {t("leads.lost")}
              </Button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setLosing(true)}
              className="text-sm font-medium text-slate-500 hover:text-slate-700"
            >
              {t("leads.didntJoin")}
            </button>
          )}
        </>
      )}
      {lead.status === "lost" && (
        <Button
          variant="secondary"
          onClick={() =>
            void run(
              () => leadsApi.update(lead.id, { status: "contacted" }),
              t("leads.reopened"),
            )
          }
        >
          {t("leads.reopen")}
        </Button>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}
