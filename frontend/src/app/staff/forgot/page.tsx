"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { AuthShell } from "@/components/staff/AuthShell";
import { t } from "@/i18n";
import { authApi, errorMessage } from "@/lib/api";

type Step = "ask" | "confirm" | "done";

/**
 * Forgot password (PLAN.md §16.1): a code to the email or phone the account
 * signs in with, then a new password. The answer to "send me a code" is the
 * same whether or not the account exists.
 */
export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("ask");
  const [identifier, setIdentifier] = useState("");
  const [minutes, setMinutes] = useState(10);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  const sendCode = () =>
    run(async () => {
      const { expires_in } = await authApi.requestPasswordReset(identifier);
      setMinutes(Math.round(expires_in / 60));
      setCode("");
      setStep("confirm");
    });

  const back = (
    <Link href="/staff/login" className="font-semibold text-brand-700 hover:underline">
      {t("forgot.back")}
    </Link>
  );

  if (step === "done") {
    return (
      <AuthShell title={t("forgot.title")}>
        <div className="mt-5 space-y-4">
          <Notice tone="success">{t("forgot.done")}</Notice>
          <Button size="lg" block onClick={() => router.push("/staff/login")}>
            {t("forgot.signIn")}
          </Button>
        </div>
      </AuthShell>
    );
  }

  if (step === "confirm") {
    return (
      <AuthShell title={t("forgot.title")} footer={back}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await authApi.confirmPasswordReset(identifier, code, password);
              setStep("done");
            });
          }}
          className="mt-5 space-y-4"
        >
          <Notice>{t("forgot.sent", { identifier, minutes })}</Notice>
          <Field
            label={t("forgot.code")}
            value={code}
            onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            name="code"
          />
          <Field
            label={t("forgot.newPassword")}
            value={password}
            onChange={setPassword}
            type="password"
            required
            autoComplete="new-password"
            help={t("forgot.newPasswordHelp")}
            name="new-password"
          />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" size="lg" block disabled={pending}>
            {pending ? t("forgot.saving") : t("forgot.save")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            block
            disabled={pending}
            onClick={() => void sendCode()}
          >
            {t("forgot.resend")}
          </Button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t("forgot.title")} footer={back}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void sendCode();
        }}
        className="mt-5 space-y-4"
      >
        <p className="text-sm text-slate-600">{t("forgot.intro")}</p>
        <Field
          label={t("login.identifier")}
          value={identifier}
          onChange={setIdentifier}
          required
          autoComplete="username"
          name="identifier"
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" size="lg" block disabled={pending}>
          {pending ? t("forgot.sending") : t("forgot.send")}
        </Button>
      </form>
    </AuthShell>
  );
}
