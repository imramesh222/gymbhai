"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { QrCode } from "@/components/QrCode";
import { t } from "@/i18n";
import { errorMessage, twoStepApi } from "@/lib/api";

/** The secret in groups of four, as people read it off a screen. */
function grouped(secret: string): string {
  return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
}

/**
 * Recovery codes, shown once: only their hashes are kept. Copy, download or
 * print them, and confirm before moving on.
 */
export function RecoveryCodes({
  codes,
  onDone,
}: {
  codes: string[];
  onDone: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");
  return (
    <div className="space-y-4">
      <Notice tone="warning">{t("twoStep.codesIntro")}</Notice>
      <ol
        aria-label={t("twoStep.codesTitle")}
        className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-4 font-mono text-sm text-slate-900 ring-1 ring-hairline"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() =>
            navigator.clipboard
              ?.writeText(text)
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {copied ? t("twoStep.copied") : t("twoStep.copy")}
        </Button>
        <a
          href={`data:text/plain;charset=utf-8,${encodeURIComponent(
            `${t("twoStep.codesFileHeading")}\n\n${text}\n`,
          )}`}
          download="gymbhai-recovery-codes.txt"
          className="inline-flex items-center rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-card ring-1 ring-hairline transition hover:bg-slate-50"
        >
          {t("twoStep.download")}
        </a>
      </div>
      <Button type="button" block onClick={onDone}>
        {t("twoStep.savedThem")}
      </Button>
    </div>
  );
}

type Step =
  | { kind: "password" }
  | { kind: "scan"; secret: string; uri: string }
  | { kind: "codes"; codes: string[] };

/**
 * Turning on two-step sign-in (PLAN.md §16.1): the password again, then the
 * QR code for the authenticator app and a first code from it, then the
 * recovery codes. `onDone` runs once the codes have been saved.
 */
export function TwoStepSetup({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<Step>({ kind: "password" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
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

  if (step.kind === "codes")
    return <RecoveryCodes codes={step.codes} onDone={onDone} />;

  if (step.kind === "scan") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            const { recovery_codes } = await twoStepApi.enable(code);
            setStep({ kind: "codes", codes: recovery_codes });
          });
        }}
        className="space-y-4"
      >
        <p className="text-sm text-slate-600">{t("twoStep.scanIntro")}</p>
        <div className="flex justify-center">
          <QrCode value={step.uri} size={200} label={t("twoStep.qrLabel")} />
        </div>
        <div className="text-center">
          <p className="text-xs text-slate-500">{t("twoStep.typeInstead")}</p>
          <p
            data-testid="two-step-secret"
            className="mt-1 font-mono text-sm tracking-wide break-all text-slate-900 select-all"
          >
            {grouped(step.secret)}
          </p>
        </div>
        <Field
          label={t("twoStep.code")}
          value={code}
          onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
          required
          inputMode="numeric"
          autoComplete="one-time-code"
          name="code"
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {t("twoStep.turnOn")}
        </Button>
      </form>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          const { secret, uri } = await twoStepApi.setup(password);
          setStep({ kind: "scan", secret, uri });
        });
      }}
      className="space-y-4"
    >
      <p className="text-sm text-slate-600">{t("twoStep.setupIntro")}</p>
      <Field
        label={t("twoStep.yourPassword")}
        value={password}
        onChange={setPassword}
        type="password"
        required
        autoComplete="current-password"
        name="password"
      />
      {error && <Notice tone="error">{error}</Notice>}
      <Button type="submit" block disabled={pending}>
        {t("twoStep.continue")}
      </Button>
    </form>
  );
}
