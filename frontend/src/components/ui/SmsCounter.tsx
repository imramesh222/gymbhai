import { t } from "@/i18n";
import { isGsm, smsParts } from "@/lib/sms";

/** "2 SMS · Nepali uses 70 characters per SMS" under a message box. */
export function SmsCounter({ text }: { text: string }) {
  const parts = smsParts(text);
  return (
    <p className={`mt-1 text-xs ${parts > 1 ? "text-amber-700" : "text-slate-500"}`}>
      {t("sms.parts", { count: parts, characters: text.length })}
      {text && !isGsm(text) && ` · ${t("sms.unicode")}`}
    </p>
  );
}
