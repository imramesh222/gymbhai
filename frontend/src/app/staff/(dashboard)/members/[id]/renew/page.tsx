"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { PlanMonthsQuestion } from "@/components/settings/PlanMonthsQuestion";
import {
  emptySale,
  SaleForm,
  saleTotal,
  toSaleInput,
  type SaleDraft,
} from "@/components/money/SaleForm";
import { ActionBar } from "@/components/ui/ActionBar";
import { Card, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { branchesApi, errorMessage, membersApi, plansApi } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";
import { enterMovesOn } from "@/lib/forms";
import { useIdempotencyKey } from "@/lib/idempotency";
import { PageSkeleton } from "@/components/ui/Skeleton";

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

  const saving = useIdempotencyKey();
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <PageSkeleton label={t("common.loading")} />;
  const [member, plans, branches] = data;
  const draft = sale ?? emptySale(member.renewal_starts_on, member.home_branch_id);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.planId) return setSaveError(t("sale.choosePlan"));
    setPending(true);
    setSaveError(null);
    try {
      const body = toSaleInput(draft);
      const result = await membersApi.sell(member.id, body, saving.keyFor(body));
      saving.succeeded();
      router.push(
        `/staff/members/${member.id}${result.payment ? `?receipt=${result.payment.id}` : ""}`,
      );
    } catch (err) {
      setSaveError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={(e) => void submit(e)}
      onKeyDown={enterMovesOn}
      className="space-y-4"
    >
      <PageHeader
        title={member.status === "none" ? t("member.sell") : t("member.renew")}
        subtitle={`${member.name} · ${member.member_code}`}
      />
      {member.valid_until && member.status !== "expired" && (
        <Notice>{t("renew.queued", { date: date(member.renewal_starts_on) })}</Notice>
      )}
      {calendar ? (
        <Card>
          <SaleForm
            plans={plans}
            branches={branches}
            value={draft}
            onChange={setSale}
            calendar={calendar}
            display={display}
            firstMembership={member.first_membership}
            payer={{ id: member.id, name: member.name, phone: member.phone }}
          />
        </Card>
      ) : (
        <PlanMonthsQuestion />
      )}
      {saveError && <Notice tone="error">{saveError}</Notice>}
      <ActionBar>
        <span className="text-sm text-slate-600">
          {t("sale.total")}{" "}
          <Money
            paisa={saleTotal(draft)}
            className="text-lg font-semibold text-slate-900"
          />
        </span>
        <Button type="submit" disabled={pending}>
          {pending ? t("common.saving") : t("renew.save")}
        </Button>
      </ActionBar>
    </form>
  );
}
