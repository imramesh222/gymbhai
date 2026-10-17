import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/LegalPage";
import { t } from "@/i18n";
import { terms } from "@/i18n/legal.en";

export const metadata: Metadata = { title: terms.title };

export default function TermsPage() {
  return (
    <LegalPage
      document={terms}
      other={{ href: "/privacy", label: t("legal.privacy") }}
    />
  );
}
