"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
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
    if (!loading && me) router.replace("/staff");
  }, [loading, me, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await signIn(identifier, password);
      router.push("/staff");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4 py-10">
      <h1 className="text-2xl font-bold text-brand-900">{t("login.title")}</h1>
      <form onSubmit={(e) => void submit(e)} className="mt-6 space-y-4">
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
        <Button type="submit" block disabled={pending}>
          {pending ? t("login.submitting") : t("login.submit")}
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        {t("login.newGym")}{" "}
        <Link href="/signup" className="font-medium text-brand-700 hover:underline">
          {t("home.signUp")}
        </Link>
      </p>
    </main>
  );
}
