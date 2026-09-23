"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { LogoMark } from "@/components/ui/Logo";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function StaffLoginPage() {
  const { me, loading, signIn } = useAuth();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already signed in (a returning tab): go straight in.
  useEffect(() => {
    if (!loading && me)
      router.replace(me.staff.is_platform_admin ? "/admin" : "/staff");
  }, [loading, me, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const signedIn = await signIn(identifier, password);
      router.push(signedIn.staff.is_platform_admin ? "/admin" : "/staff");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <main className="relative isolate flex min-h-dvh flex-col justify-center px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-[radial-gradient(70%_70%_at_50%_0%,var(--color-brand-200),transparent)] opacity-70"
      />
      <div className="mx-auto w-full max-w-sm">
        <Link href="/" className="mx-auto flex w-fit items-center gap-2.5">
          <LogoMark />
          <span className="text-lg font-bold tracking-tight text-slate-900">
            {t("app.name")}
          </span>
        </Link>
        <div className="mt-6 rounded-2xl bg-surface p-6 shadow-raised ring-1 ring-hairline">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            {t("login.title")}
          </h1>
          <form onSubmit={(e) => void submit(e)} className="mt-5 space-y-4">
            <Field
              label={t("login.identifier")}
              value={identifier}
              onChange={setIdentifier}
              required
              autoComplete="username"
              name="identifier"
            />
            <Field
              label={t("login.password")}
              value={password}
              onChange={setPassword}
              type="password"
              required
              autoComplete="current-password"
              name="password"
            />
            {error && <Notice tone="error">{error}</Notice>}
            <Button type="submit" size="lg" block disabled={pending}>
              {pending ? t("login.submitting") : t("login.submit")}
            </Button>
          </form>
        </div>
        <p className="mt-5 text-center text-sm text-slate-600">
          {t("login.newGym")}{" "}
          <Link href="/signup" className="font-semibold text-brand-700 hover:underline">
            {t("home.signUp")}
          </Link>
        </p>
      </div>
    </main>
  );
}
