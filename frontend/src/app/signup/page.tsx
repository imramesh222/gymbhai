"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AuthSplit } from "@/components/AuthSplit";
import { Button } from "@/components/Button";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Trans } from "@/components/Trans";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import { memberAppUrl, slugify } from "@/lib/slug";

/** "YOUR GYM" between two hairlines. */
const SECTION_HEADING =
  "flex items-center gap-3 text-xs font-semibold tracking-wider text-slate-500 uppercase before:h-px before:flex-1 before:bg-hairline after:h-px after:flex-1 after:bg-hairline";

export default function SignupPage() {
  const { registerGym } = useAuth();
  const router = useRouter();
  // Sent by another gym: /signup?ref=their-address (§16.5, 10.5).
  const ref = useSearchParams().get("ref");
  // The language they sign up in is the gym's (§16.6).
  const { locale } = useLocale();

  const [gymName, setGymName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [branchName, setBranchName] = useState(t("signup.branchDefault"));
  const [ownerName, setOwnerName] = useState("");
  const [ownerPhone, setOwnerPhone] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function changeGymName(value: string) {
    setGymName(value);
    if (!slugEdited) setSlug(slugify(value));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!acceptTerms) {
      setError(t("signup.acceptTermsNeeded"));
      return;
    }
    setPending(true);
    setError(null);
    try {
      await registerGym({
        gym_name: gymName,
        slug,
        branch_name: branchName,
        owner_name: ownerName,
        owner_phone: ownerPhone,
        owner_email: ownerEmail,
        password,
        accept_terms: acceptTerms,
        ref,
        language: locale,
      });
      router.push("/staff");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <AuthSplit title={t("signup.title")} subtitle={t("signup.subtitle")}>
      <form onSubmit={(e) => void submit(e)} className="mt-8 space-y-7">
        <section className="space-y-4">
          <h2 className={SECTION_HEADING}>{t("signup.section.gym")}</h2>
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
          <div>
            <p className="mb-1.5 text-sm font-medium text-slate-700">
              {t("signup.language")}
            </p>
            <LanguageSwitch />
            <p className="mt-1.5 text-sm text-slate-500">{t("signup.languageHelp")}</p>
          </div>
        </section>

        <section className="space-y-4">
          <h2 className={SECTION_HEADING}>{t("signup.section.owner")}</h2>
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

        <label className="flex cursor-pointer items-start gap-3 px-1 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={acceptTerms}
            onChange={(e) => setAcceptTerms(e.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-brand-600"
          />
          <span>
            <Trans
              k="signup.acceptTerms"
              parts={{
                terms: (
                  <Link
                    href="/terms"
                    target="_blank"
                    className="font-semibold text-brand-700 hover:underline"
                  >
                    {t("signup.termsLink")}
                  </Link>
                ),
                privacy: (
                  <Link
                    href="/privacy"
                    target="_blank"
                    className="font-semibold text-brand-700 hover:underline"
                  >
                    {t("signup.privacyLink")}
                  </Link>
                ),
              }}
            />
          </span>
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" size="lg" block disabled={pending}>
          {pending ? t("signup.submitting") : t("signup.submit")}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-600">
        {t("signup.haveAccount")}{" "}
        <Link
          href="/staff/login"
          className="font-semibold text-brand-700 hover:underline"
        >
          {t("home.signIn")}
        </Link>
      </p>
    </AuthSplit>
  );
}
