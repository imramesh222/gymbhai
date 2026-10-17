import Link from "next/link";

import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import type { LegalDocument } from "@/i18n/legal.en";

/** The terms of service and the privacy policy: readable, and printable. */
export function LegalPage({
  document,
  other,
}: {
  document: LegalDocument;
  other: { href: string; label: string };
}) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 sm:py-14">
      <Link href="/" className="flex w-fit items-center gap-2.5 print:hidden">
        <LogoMark />
        <span className="text-lg font-bold tracking-tight text-slate-900">
          {t("app.name")}
        </span>
      </Link>
      <article className="mt-8 rounded-2xl bg-surface p-6 shadow-card ring-1 ring-hairline sm:p-10 print:p-0 print:shadow-none print:ring-0">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">
          {document.title}
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          {t("legal.updated", { date: document.updated })}
        </p>
        <p className="mt-6 text-base leading-relaxed text-slate-700">
          {document.intro}
        </p>
        {document.sections.map((section) => (
          <section key={section.heading} className="mt-8">
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">
              {section.heading}
            </h2>
            {section.paragraphs?.map((text) => (
              <p key={text} className="mt-3 leading-relaxed text-slate-700">
                {text}
              </p>
            ))}
            {section.bullets && (
              <ul className="mt-3 list-disc space-y-2 pl-5 leading-relaxed text-slate-700">
                {section.bullets.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </article>
      <p className="mt-6 text-sm print:hidden">
        <Link
          href={other.href}
          className="font-semibold text-brand-700 hover:underline"
        >
          {other.label}
        </Link>
      </p>
    </main>
  );
}
