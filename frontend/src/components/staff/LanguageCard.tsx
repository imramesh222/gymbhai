"use client";

import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { errorMessage, languageApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Choice = "gym" | "en" | "ne";

/** My account → Language (PLAN.md §16.6): their own, or the gym's. */
export function LanguageCard() {
  const { me, refreshMe } = useAuth();
  const toast = useToast();
  if (!me) return null;
  const value: Choice = me.own_language ?? "gym";
  const gymLanguage = me.gym?.settings.language === "ne" ? "नेपाली" : "English";
  return (
    <Card title={t("language.title")}>
      <Select<Choice>
        label={t("language.mine")}
        value={value}
        onChange={async (choice) => {
          try {
            await languageApi.set(choice === "gym" ? null : choice);
            await refreshMe(); // the screen follows the account's language
          } catch (err) {
            toast.error(errorMessage(err));
          }
        }}
        options={[
          { value: "gym", label: t("language.gymDefault", { language: gymLanguage }) },
          { value: "en", label: "English" },
          { value: "ne", label: "नेपाली" },
        ]}
      />
    </Card>
  );
}
