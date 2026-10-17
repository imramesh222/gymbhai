"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { AuthShell } from "@/components/staff/AuthShell";
import { t } from "@/i18n";
import { ApiError, errorMessage } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";

export default function StaffLoginPage() {
  const { me, loading, signIn, completeTwoStep } = useAuth();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  // Set once the password was right and two-step sign-in is on.
  const [twoStepToken, setTwoStepToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already signed in (a returning tab): go straight in.
  useEffect(() => {
    if (!loading && me) router.replace(homeFor(me));
  }, [loading, me, router]);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      // The five minutes for the code ran out: start again from the password.
      if (err instanceof ApiError && err.code === "two_step_expired") {
        setTwoStepToken(null);
        setCode("");
      }
      setError(errorMessage(err));
      setPending(false);
    }
  }

  const submitPassword = () =>
    run(async () => {
      const result = await signIn(identifier, password);
      if ("twoStepToken" in result) {
        setTwoStepToken(result.twoStepToken);
        setPending(false);
      } else {
        router.push(homeFor(result.me));
      }
    });

  const submitCode = (token: string) =>
    run(async () => {
      router.push(homeFor(await completeTwoStep(token, code)));
    });

  if (twoStepToken) {
    return (
      <AuthShell title={t("twoStep.loginTitle")}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submitCode(twoStepToken);
          }}
          className="mt-5 space-y-4"
        >
          <p className="text-sm text-slate-600">
            {t(useRecovery ? "twoStep.loginRecoveryIntro" : "twoStep.loginIntro")}
          </p>
          {useRecovery ? (
            <Field
              key="recovery"
              label={t("twoStep.recoveryCode")}
              value={code}
              onChange={setCode}
              required
              autoComplete="off"
              name="recovery-code"
            />
          ) : (
            <Field
              key="app"
              label={t("twoStep.code")}
              value={code}
              onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
              required
              inputMode="numeric"
              autoComplete="one-time-code"
              name="code"
            />
          )}
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" size="lg" block disabled={pending}>
            {pending ? t("login.submitting") : t("login.submit")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            block
            onClick={() => {
              setUseRecovery(!useRecovery);
              setCode("");
              setError(null);
            }}
          >
            {t(useRecovery ? "twoStep.useApp" : "twoStep.useRecovery")}
          </Button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={t("login.title")}
      footer={
        <>
          {t("login.newGym")}{" "}
          <Link href="/signup" className="font-semibold text-brand-700 hover:underline">
            {t("home.signUp")}
          </Link>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submitPassword();
        }}
        className="mt-5 space-y-4"
      >
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
        <p className="text-center text-sm">
          <Link
            href="/staff/forgot"
            className="font-medium text-brand-700 hover:underline"
          >
            {t("login.forgot")}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
