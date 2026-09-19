"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import {
  emptySale,
  SaleForm,
  toSaleInput,
  type SaleDraft,
} from "@/components/money/SaleForm";
import { Card, PageHeader } from "@/components/ui/Card";
import { Checkbox, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import {
  branchesApi,
  errorMessage,
  membersApi,
  plansApi,
  type Member,
  type PhoneMatch,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Add a member and, in the same save, sell their first membership (§5.3). */
export default function NewMemberPage() {
  const router = useRouter();
  const { can } = useAuth();
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
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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
  const shown = phone.replace(/\D/g, "").length >= 10 ? matches : [];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (selling && !sale.planId) return setError(t("sale.choosePlan"));
    setPending(true);
    setError(null);
    try {
      const result = await membersApi.create({
        name,
        phone,
        email: email || null,
        gender: (gender || null) as Member["gender"],
        home_branch_id: home || null,
        membership: selling
          ? toSaleInput({ ...sale, branchId: sale.branchId || home })
          : null,
      });
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
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      <PageHeader title={t("members.add")} />
      <Card title={t("member.details")}>
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
          {branches.length > 1 && (
            <Select
              label={t("member.homeBranch")}
              value={home}
              onChange={setBranchId}
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
            />
          )}
        </div>
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
          {selling && (
            <SaleForm
              plans={plans}
              branches={branches}
              value={{ ...sale, branchId: sale.branchId || home }}
              onChange={setSale}
              calendar={calendar}
              display={display}
              firstMembership
            />
          )}
        </Card>
      )}

      {error && <Notice tone="error">{error}</Notice>}
      <Button type="submit" block disabled={pending}>
        {pending ? t("common.saving") : t("members.save")}
      </Button>
    </form>
  );
}
