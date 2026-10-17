"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, Select, TextArea } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import {
  errorMessage,
  LEAD_SOURCES,
  leadsApi,
  type Lead,
  type LeadMatch,
  type LeadSource,
  type Plan,
} from "@/lib/api";
import { addDays, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";

/** Someone asked about joining: who, how to reach them, and when to call back. */
export function AddLead({
  plans,
  onClose,
  onAdded,
}: {
  plans: Plan[];
  onClose: () => void;
  onAdded: (lead: Lead) => void;
}) {
  const { display } = useGymCalendar();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [source, setSource] = useState<LeadSource>("walk_in");
  const [planId, setPlanId] = useState("");
  const [followUp, setFollowUp] = useState(addDays(todayInNepal(), 1));
  const [referrer, setReferrer] = useState<Picked | null>(null);
  const [notes, setNotes] = useState("");
  const [matches, setMatches] = useState<LeadMatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already a member, or asked before? A warning, as on Add member.
  useEffect(() => {
    if (phone.replace(/\D/g, "").length < 10) return;
    const timer = setTimeout(() => {
      leadsApi
        .phoneCheck(phone)
        .then(setMatches)
        .catch(() => setMatches([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [phone]);
  const shown = phone.replace(/\D/g, "").length >= 10 ? matches : [];

  return (
    <Dialog open onClose={onClose} title={t("leads.add")}>
      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setPending(true);
          setError(null);
          try {
            const lead = await leadsApi.create({
              name,
              phone: phone || null,
              email: email || null,
              source: referrer ? "referral" : source,
              plan_id: planId || null,
              follow_up_on: followUp || null,
              referred_by_id: referrer?.id ?? null,
              notes: notes || null,
            });
            onAdded(lead);
          } catch (err) {
            setError(errorMessage(err));
            setPending(false);
          }
        }}
      >
        <Field label={t("member.name")} value={name} onChange={setName} required />
        <div>
          <Field
            label={t("member.phone")}
            value={phone}
            onChange={setPhone}
            type="tel"
            inputMode="tel"
          />
          {shown.length > 0 && (
            <p className="mt-1 text-xs text-amber-800" role="status">
              {t("leads.phoneKnown", {
                names: shown
                  .map((m) =>
                    m.kind === "member"
                      ? t("leads.isMember", { name: m.name })
                      : t("leads.askedBefore", { name: m.name }),
                  )
                  .join(", "),
              })}
            </p>
          )}
        </div>
        <Field
          label={t("member.email")}
          value={email}
          onChange={setEmail}
          type="email"
          optional
          optionalLabel={t("common.optional")}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label={t("leads.source")}
            value={referrer ? "referral" : source}
            onChange={setSource}
            options={LEAD_SOURCES.map((s) => ({
              value: s,
              label: t(`leads.source.${s}` as MessageKey),
            }))}
          />
          <Select
            label={t("leads.plan")}
            value={planId}
            onChange={setPlanId}
            options={[
              { value: "", label: t("leads.noPlan") },
              ...plans.map((p) => ({ value: p.id, label: p.name })),
            ]}
          />
        </div>
        <MemberPicker
          label={t("leads.referredBy")}
          value={referrer}
          onChange={setReferrer}
        />
        <DateInput
          label={t("leads.followUpOn")}
          value={followUp}
          onChange={setFollowUp}
          display={display}
        />
        <TextArea label={t("leads.notes")} value={notes} onChange={setNotes} />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {t("leads.save")}
        </Button>
      </form>
    </Dialog>
  );
}
