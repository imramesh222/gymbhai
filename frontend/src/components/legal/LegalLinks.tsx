import Link from "next/link";

import { t } from "@/i18n";

/** "Terms of service · Privacy policy", for the foot of public pages. */
export function LegalLinks({ privacyOnly = false }: { privacyOnly?: boolean }) {
  const link = "transition hover:text-slate-700 hover:underline";
  return (
    <nav
      aria-label={t("legal.links")}
      className="mt-8 flex justify-center gap-3 text-xs text-slate-500 print:hidden"
    >
      {!privacyOnly && (
        <>
          <Link href="/terms" className={link}>
            {t("legal.terms")}
          </Link>
          <span aria-hidden>·</span>
        </>
      )}
      <Link href="/privacy" className={link}>
        {t("legal.privacy")}
      </Link>
    </nav>
  );
}
