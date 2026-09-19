import Link from "next/link";

import { t } from "@/i18n";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-brand-900">
        {t("app.name")}
      </h1>
      <p className="mt-2 text-lg text-slate-700">{t("app.tagline")}</p>
      <p className="mt-4 text-slate-600">{t("home.pitch")}</p>
      <div className="mt-8 flex flex-col gap-3">
        <Link
          href="/signup"
          className="rounded-lg bg-brand-600 px-4 py-3 text-center font-semibold text-white hover:bg-brand-700"
        >
          {t("home.signUp")}
        </Link>
        <Link
          href="/staff/login"
          className="rounded-lg border border-slate-300 bg-white px-4 py-3 text-center font-semibold text-slate-800 hover:bg-slate-50"
        >
          {t("home.signIn")}
        </Link>
      </div>
    </main>
  );
}
