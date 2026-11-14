import type { Metadata } from "next";
import { headers } from "next/headers";

import { LegalPage } from "@/components/legal/LegalPage";
import { t } from "@/i18n";
import { contactEmail, privacy } from "@/i18n/legal.en";

export const metadata: Metadata = { title: privacy.title };

export default async function PrivacyPage() {
  const host = (await headers()).get("host") ?? "";
  return (
    <LegalPage
      document={privacy}
      contact={contactEmail(host)}
      other={{ href: "/terms", label: t("legal.terms") }}
    />
  );
}
