"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Choice } from "@/components/Choice";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import { errorMessage, type DateDisplay, type PlanMonths } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { memberAppUrl, slugify } from "@/lib/slug";

export default function SignupPage() {
  const { registerGym } = useAuth();
  const router = useRouter();

  const [gymName, setGymName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [branchName, setBranchName] = useState(t("signup.branchDefault"));
  // No defaults: the owner must choose both (PLAN.md §5.1).
  const [planMonths, setPlanMonths] = useState<PlanMonths | null>(null);
  const [dateDisplay, setDateDisplay] = useState<DateDisplay | null>(null);
  const [ownerName, setOwnerName] = useState("");
  const [ownerPhone, setOwnerPhone] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function changeGymName(value: string) {
    setGymName(value);
    if (!slugEdited) setSlug(slugify(value));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!planMonths || !dateDisplay) {
      setError(t("signup.chooseCalendar"));
      return;
    }
    setPending(true);
    setError(null);
    try {
      await registerGym({
        gym_name: gymName,
        slug,
        branch_name: branchName,
        plan_months: planMonths,
        date_display: dateDisplay,
        owner_name: ownerName,
        owner_phone: ownerPhone,
        owner_email: ownerEmail,
        password,
      });
      router.push("/staff");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <main className="relative isolate mx-auto max-w-lg px-4 py-10 sm:px-6">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-80 bg-[radial-gradient(70%_70%_at_50%_0%,var(--color-brand-200),transparent)] opacity-70"
      />
      <Link href="/" className="flex w-fit items-center gap-2.5">
        <LogoMark />
        <span className="text-lg font-bold tracking-tight text-slate-900">
          {t("app.name")}
        </span>
      </Link>
      <h1 className="mt-6 text-3xl font-bold tracking-tight text-slate-900">
        {t("signup.title")}
      </h1>
      <p className="mt-2 text-slate-600">{t("signup.subtitle")}</p>

      <form onSubmit={(e) => void submit(e)} className="mt-7 space-y-5">
        <section className="space-y-4 rounded-2xl bg-surface p-5 shadow-card ring-1 ring-hairline sm:p-6">
          <h2 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            {t("signup.section.gym")}
          </h2>
          <Field
            label={t("signup.gymName")}
            value={gymName}
            onChange={changeGymName}
            required
            autoComplete="organization"
          />
          <Field
            label={t("signup.slug")}
            value={slug}
            onChange={(value) => {
              setSlugEdited(true);
              setSlug(value.toLowerCase());
            }}
            prefix="app.gymbhai.com/"
            required
            help={t("signup.slugHelp", { url: memberAppUrl(slug) })}
          />
          <Field
            label={t("signup.branchName")}
            value={branchName}
            onChange={setBranchName}
            required
          />
        </section>

        <section className="space-y-4 rounded-2xl bg-surface p-5 shadow-card ring-1 ring-hairline sm:p-6">
          <h2 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            {t("signup.section.calendar")}
          </h2>
          <Choice<PlanMonths>
            legend={t("signup.planMonths")}
            name="plan_months"
            value={planMonths}
            onChange={setPlanMonths}
            required
            options={[
              {
                value: "bs",
                label: t("signup.planMonths.bs"),
                hint: t("signup.planMonths.bsExample"),
              },
              {
                value: "ad",
                label: t("signup.planMonths.ad"),
                hint: t("signup.planMonths.adExample"),
              },
            ]}
          />
          <Choice<DateDisplay>
            legend={t("signup.dateDisplay")}
            name="date_display"
            value={dateDisplay}
            onChange={setDateDisplay}
            required
            columns={3}
            options={[
              { value: "bs", label: t("signup.dateDisplay.bs") },
              { value: "ad", label: t("signup.dateDisplay.ad") },
              { value: "both", label: t("signup.dateDisplay.both") },
            ]}
          />
          <p className="text-sm text-slate-500">{t("signup.calendarHelp")}</p>
        </section>

        <section className="space-y-4 rounded-2xl bg-surface p-5 shadow-card ring-1 ring-hairline sm:p-6">
          <h2 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            {t("signup.section.owner")}
          </h2>
          <Field
            label={t("signup.ownerName")}
            value={ownerName}
            onChange={setOwnerName}
            required
            autoComplete="name"
          />
          <Field
            label={t("signup.ownerPhone")}
            value={ownerPhone}
            onChange={setOwnerPhone}
            type="tel"
            inputMode="tel"
            required
            autoComplete="tel"
          />
          <Field
            label={t("signup.ownerEmail")}
            value={ownerEmail}
            onChange={setOwnerEmail}
            type="email"
            optional
            optionalLabel={t("common.optional")}
            autoComplete="email"
          />
          <Field
            label={t("signup.password")}
            value={password}
            onChange={setPassword}
            type="password"
            required
            autoComplete="new-password"
            help={t("signup.passwordHelp")}
          />
        </section>

        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" size="lg" block disabled={pending}>
          {pending ? t("signup.submitting") : t("signup.submit")}
        </Button>
      </form>

      <p className="mt-6 text-sm text-slate-600">
        {t("signup.haveAccount")}{" "}
        <Link
          href="/staff/login"
          className="font-semibold text-brand-700 hover:underline"
        >
          {t("home.signIn")}
        </Link>
      </p>
    </main>
  );
}
