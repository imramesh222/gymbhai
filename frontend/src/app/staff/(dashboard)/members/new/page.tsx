"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { PlanMonthsQuestion } from "@/components/settings/PlanMonthsQuestion";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
import { PhotoCapture } from "@/components/member/PhotoCapture";
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
import { useToast } from "@/components/ui/Toast";
import { Checkbox, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import {
  branchesApi,
  errorMessage,
  leadsApi,
  membersApi,
  plansApi,
  type Member,
  type PhoneMatch,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";
import { enterMovesOn } from "@/lib/forms";
import { useIdempotencyKey } from "@/lib/idempotency";

/** Add a member and, in the same save, sell their first membership (§5.3). */
export default function NewMemberPage() {
  const router = useRouter();
  const { can, me } = useAuth();
  const { calendar, display } = useGymCalendar();
  const setup = useLoad(() => Promise.all([plansApi.list(), branchesApi.list()]), []);
  const [plans, branches] = setup.data ?? [[], []];

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [gender, setGender] = useState<"" | "male" | "female" | "other">("");
  const [branchId, setBranchId] = useState("");
  const [matches, setMatches] = useState<PhoneMatch[]>([]);
  const [selling, setSelling] = useState(can("memberships.sell"));
  const [sale, setSale] = useState<SaleDraft>(() => emptySale(todayInNepal(), ""));
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [referrer, setReferrer] = useState<Picked | null>(null);
  const [whatsapp, setWhatsapp] = useState(false);
  // Convert (§16.4, 9.1): Add member opened from an enquiry, filled in.
  const leadId = useSearchParams().get("lead");
  const lead = useLoad(
    () =>
      leadId && can("leads.manage") ? leadsApi.get(leadId) : Promise.resolve(null),
    [leadId],
  );
  const [filledFrom, setFilledFrom] = useState<string | null>(null);
  if (lead.data && filledFrom !== lead.data.id) {
    // Once, as the enquiry arrives: what was typed after that stays.
    const from = lead.data;
    setFilledFrom(from.id);
    setName(from.name);
    setPhone(from.phone ?? "");
    setEmail(from.email ?? "");
    setBranchId(from.branch_id);
    if (from.referred_by_id && from.referred_by_name) {
      setReferrer({ id: from.referred_by_id, name: from.referred_by_name });
    }
  }
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const toast = useToast();

  const home = branchId || branches[0]?.id || "";

  // Warn when the number is already on file: families often share one (§5.5).
  useEffect(() => {
    if (phone.replace(/\D/g, "").length < 10) return;
    const timer = setTimeout(() => {
      membersApi
        .phoneCheck(phone)
        .then(setMatches)
        .catch(() => setMatches([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [phone]);
  const saving = useIdempotencyKey();
  const shown = phone.replace(/\D/g, "").length >= 10 ? matches : [];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (selling && !sale.planId) return setError(t("sale.choosePlan"));
    setPending(true);
    setError(null);
    try {
      const body = {
        name,
        phone,
        email: email || null,
        gender: (gender || null) as Member["gender"],
        home_branch_id: home || null,
        referred_by_id: referrer?.id ?? null,
        whatsapp_agreed: whatsapp,
        lead_id: leadId,
        membership: selling
          ? toSaleInput({ ...sale, branchId: sale.branchId || home })
          : null,
      };
      // Saved once even if Save is tapped again after a lost answer.
      const result = await membersApi.create(body, saving.keyFor(body));
      saving.succeeded();
      if (photo) {
        // The member is saved either way; a photo can be added again later.
        await membersApi
          .uploadPhoto(result.member.id, photo)
          .catch(() => toast.error(t("photo.uploadFailed")));
      }
      const payment = result.payment_id;
      router.push(
        `/staff/members/${result.member.id}${payment ? `?receipt=${payment}` : ""}`,
      );
    } catch (err) {
      setError(errorMessage(err));
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
        title={t("members.add")}
        subtitle={
          lead.data
            ? t("leads.converting", {
                name: lead.data.name,
                plan: lead.data.plan_name ?? "—",
              })
            : undefined
        }
      />
      <Card title={t("member.details")}>
        <div className="mb-4">
          <PhotoCapture photo={photo} onChange={setPhoto} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("member.name")} value={name} onChange={setName} required />
          <div>
            <Field
              label={t("member.phone")}
              value={phone}
              onChange={setPhone}
              type="tel"
              inputMode="tel"
              required
              name="phone"
            />
            {shown.length > 0 && (
              <p className="mt-1 text-xs text-amber-800" role="status">
                {t("member.phoneShared", {
                  names: shown.map((m) => m.name).join(", "),
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
          <Select
            label={t("member.gender")}
            value={gender}
            onChange={setGender}
            options={[
              { value: "female", label: t("member.gender.female") },
              { value: "male", label: t("member.gender.male") },
              { value: "other", label: t("member.gender.other") },
            ]}
          />
          <MemberPicker
            label={t("leads.referredBy")}
            value={referrer}
            onChange={setReferrer}
          />
          {branches.length > 1 && (
            <Select
              label={t("member.homeBranch")}
              value={home}
              onChange={setBranchId}
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
            />
          )}
        </div>
        {me?.gym?.whatsapp_available && (
          <div className="mt-3">
            <Checkbox
              label={t("member.whatsappAgreed")}
              hint={t("member.whatsappAgreedHint")}
              checked={whatsapp}
              onChange={setWhatsapp}
            />
          </div>
        )}
      </Card>

      {can("memberships.sell") && (
        <Card
          title={t("members.firstMembership")}
          actions={
            <Checkbox
              label={t("members.sellNow")}
              checked={selling}
              onChange={setSelling}
            />
          }
        >
          {selling &&
            (calendar ? (
              <SaleForm
                plans={plans}
                branches={branches}
                value={{ ...sale, branchId: sale.branchId || home }}
                onChange={setSale}
                calendar={calendar}
                display={display}
                firstMembership
                payer={{ phone }}
              />
            ) : (
              <PlanMonthsQuestion />
            ))}
        </Card>
      )}

      {error && <Notice tone="error">{error}</Notice>}
      <ActionBar>
        {selling && sale.planId ? (
          <span className="text-sm text-slate-600">
            {t("sale.total")}{" "}
            <Money
              paisa={saleTotal(sale)}
              className="text-lg font-semibold text-slate-900"
            />
          </span>
        ) : (
          <span />
        )}
        <Button type="submit" disabled={pending}>
          {pending ? t("common.saving") : t("members.save")}
        </Button>
      </ActionBar>
    </form>
  );
}
