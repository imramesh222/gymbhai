"use client";

import { MessageCircle, Phone } from "lucide-react";

import { Card, PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { guides as englishGuides } from "@/i18n/help.en";
import { guides as nepaliGuides } from "@/i18n/help.ne";
import { useLocale } from "@/lib/locale";
import { useAuth } from "@/lib/auth";

/** Help: talk to us on WhatsApp or Viber, and short guides (PLAN.md §16.5, 10.3). */
export default function HelpPage() {
  const { me } = useAuth();
  const guides = useLocale().locale === "ne" ? nepaliGuides : englishGuides;
  const number = me?.support_whatsapp;
  const hello = encodeURIComponent(
    t("help.hello", { gym: me?.gym?.name ?? "", name: me?.staff.name ?? "" }),
  );
  const button =
    "inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-card transition hover:opacity-90";
  return (
    <div className="space-y-4">
      <PageHeader title={t("help.title")} subtitle={t("help.subtitle")} />
      {number && (
        <Card title={t("help.talk")}>
          <p className="mb-3 text-sm text-slate-600">{t("help.talkHelp")}</p>
          <div className="flex flex-wrap gap-2">
            <a
              href={`https://wa.me/${number}?text=${hello}`}
              target="_blank"
              rel="noreferrer"
              className={`${button} bg-[#128c4b]`}
            >
              <MessageCircle className="size-4" aria-hidden />
              {t("help.whatsapp")}
            </a>
            <a
              href={`viber://chat?number=%2B${number}`}
              className={`${button} bg-[#665ca7]`}
            >
              <Phone className="size-4" aria-hidden />
              {t("help.viber")}
            </a>
          </div>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {guides.map((guide) => (
          <Card key={guide.id} title={guide.title}>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-700">
              {guide.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            {guide.tip && <p className="mt-3 text-sm text-slate-500">{guide.tip}</p>}
          </Card>
        ))}
      </div>
    </div>
  );
}
