import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/LegalPage";
import { t } from "@/i18n";
import { privacy } from "@/i18n/legal.en";

export const metadata: Metadata = { title: privacy.title };

export default function PrivacyPage() {
  return (
    <LegalPage document={privacy} other={{ href: "/terms", label: t("legal.terms") }} />
  );
}
