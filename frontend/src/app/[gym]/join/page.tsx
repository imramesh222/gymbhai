"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Select, TextArea } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, LEAD_SOURCES } from "@/lib/api";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { formatRs } from "@/lib/money";
import { useLoad } from "@/lib/useLoad";

/**
 * "Not a member yet? Ask to join" behind the gym QR (PLAN.md §16.4, 9.5): the
 * gym gets an enquiry to call back. Nobody becomes a member from here.
 */
export default function JoinPage() {
  const { slug } = useMember();
  const gym = useLoad(() => memberApi.gym(slug), [slug]);
  const options = useLoad(() => memberApi.joinOptions(slug), [slug]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [planId, setPlanId] = useState("");
  const [source, setSource] = useState("other");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (options.error) {
    return (
      <main className="mx-auto max-w-md p-6">
        <Notice>{t("app.join.off")}</Notice>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md space-y-5 p-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        {t("app.join.title", { gym: gym.data?.name ?? "" })}
      </h1>
      {sent ? (
        <div className="space-y-3">
          <Notice tone="success">{t("app.join.sent")}</Notice>
          <Link href={`/${slug}`} className="block text-sm text-brand-700 underline">
            {t("app.join.member")}
          </Link>
        </div>
      ) : (
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setPending(true);
            setError(null);
            try {
              await memberApi.askToJoin(slug, {
                name,
                phone,
                plan_id: planId || null,
                source,
                message: message || null,
              });
              setSent(true);
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setPending(false);
            }
          }}
        >
          <p className="text-sm text-slate-600">{t("app.join.help")}</p>
          <Field label={t("member.name")} value={name} onChange={setName} required />
          <Field
            label={t("member.phone")}
            value={phone}
            onChange={setPhone}
            type="tel"
            inputMode="tel"
            required
          />
          {options.data && options.data.plans.length > 0 && (
            <Select
              label={t("leads.plan")}
              value={planId}
              onChange={setPlanId}
              options={[
                { value: "", label: t("leads.noPlan") },
                ...options.data.plans.map((p) => ({
                  value: p.id,
                  label: p.price === null ? p.name : `${p.name} — ${formatRs(p.price)}`,
                })),
              ]}
            />
          )}
          <Select
            label={t("leads.source")}
            value={source}
            onChange={setSource}
            options={LEAD_SOURCES.filter((s) => s !== "walk_in").map((s) => ({
              value: s,
              label: t(`leads.source.${s}` as MessageKey),
            }))}
          />
          <TextArea
            label={t("app.join.message")}
            value={message}
            onChange={setMessage}
          />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" block disabled={pending}>
            {t("app.join.send")}
          </Button>
        </form>
      )}
    </main>
  );
}
