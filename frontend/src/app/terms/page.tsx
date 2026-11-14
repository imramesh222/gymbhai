import type { Metadata } from "next";
import { headers } from "next/headers";

import { LegalPage } from "@/components/legal/LegalPage";
import { t } from "@/i18n";
import { contactEmail, terms } from "@/i18n/legal.en";

export const metadata: Metadata = { title: terms.title };

export default async function TermsPage() {
  const host = (await headers()).get("host") ?? "";
  return (
    <LegalPage
      document={terms}
      contact={contactEmail(host)}
      other={{ href: "/privacy", label: t("legal.privacy") }}
    />
  );
}
