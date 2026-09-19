"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import {
  emptySale,
  SaleForm,
  toSaleInput,
  type SaleDraft,
} from "@/components/money/SaleForm";
import { Card, PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { branchesApi, errorMessage, membersApi, plansApi } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/**
 * Renew (or sell a first membership to an existing member). The start date is
 * the day after the current membership ends, so early renewers lose nothing.
 */
export default function RenewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { calendar, display, date } = useGymCalendar();
  const { data, error } = useLoad(
    () => Promise.all([membersApi.get(id), plansApi.list(), branchesApi.list()]),
    [id],
  );
  const [sale, setSale] = useState<SaleDraft | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const [member, plans, branches] = data;
  const draft = sale ?? emptySale(member.renewal_starts_on, member.home_branch_id);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.planId) return setSaveError(t("sale.choosePlan"));
    setPending(true);
    setSaveError(null);
    try {
      const result = await membersApi.sell(member.id, toSaleInput(draft));
      router.push(
        `/staff/members/${member.id}${result.payment ? `?receipt=${result.payment.id}` : ""}`,
      );
    } catch (err) {
      setSaveError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      <PageHeader
        title={member.status === "none" ? t("member.sell") : t("member.renew")}
        subtitle={`${member.name} · ${member.member_code}`}
      />
      {member.valid_until && member.status !== "expired" && (
        <Notice>{t("renew.queued", { date: date(member.renewal_starts_on) })}</Notice>
      )}
      <Card>
        <SaleForm
          plans={plans}
          branches={branches}
          value={draft}
          onChange={setSale}
          calendar={calendar}
          display={display}
          firstMembership={member.first_membership}
        />
      </Card>
      {saveError && <Notice tone="error">{saveError}</Notice>}
      <Button type="submit" block disabled={pending}>
        {pending ? t("common.saving") : t("renew.save")}
      </Button>
    </form>
  );
}
