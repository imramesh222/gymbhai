"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { RecoveryCodes, TwoStepSetup } from "@/components/staff/TwoStepSetup";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { plural, t } from "@/i18n";
import { errorMessage, twoStepApi, type TwoStepStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Open = "setup" | "codes" | "off" | null;

/** A password-confirmed action: new recovery codes, or turning it off. */
function PasswordStep({
  intro,
  submitLabel,
  danger,
  onSubmit,
}: {
  intro: string;
  submitLabel: string;
  danger?: boolean;
  onSubmit: (password: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        setError(null);
        try {
          await onSubmit(password);
        } catch (err) {
          setError(errorMessage(err));
          setPending(false);
        }
      }}
      className="space-y-4"
    >
      <p className="text-sm text-slate-600">{intro}</p>
      <Field
        label={t("twoStep.yourPassword")}
        value={password}
        onChange={setPassword}
        type="password"
        required
        autoComplete="current-password"
      />
      {error && <Notice tone="error">{error}</Notice>}
      <Button
        type="submit"
        variant={danger ? "danger" : "primary"}
        block
        disabled={pending}
      >
        {submitLabel}
      </Button>
    </form>
  );
}

/** My account → Two-step sign-in (PLAN.md §16.1). */
export function TwoStepCard() {
  const { refreshMe } = useAuth();
  const [status, setStatus] = useState<TwoStepStatus | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const [newCodes, setNewCodes] = useState<string[] | null>(null);

  const load = useCallback(
    () =>
      twoStepApi
        .status()
        .then(setStatus)
        .catch(() => undefined),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);

  const close = () => {
    setOpen(null);
    setNewCodes(null);
    void load();
    void refreshMe();
  };

  if (!status) return null;
  return (
    <Card
      title={t("twoStep.title")}
      actions={
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
            status.enabled
              ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20"
              : "bg-slate-50 text-slate-600 ring-slate-500/15"
          }`}
        >
          {status.enabled ? t("twoStep.on") : t("twoStep.off")}
        </span>
      }
    >
      <p className="text-sm text-slate-600">{t("twoStep.explain")}</p>
      {status.enabled && (
        <p className="mt-2 text-sm text-slate-600">
          {plural(
            status.recovery_codes_left,
            "twoStep.codesLeftOne",
            "twoStep.codesLeft",
          )}
        </p>
      )}
      {status.required && (
        <p className="mt-2 text-sm text-slate-500">{t("twoStep.requiredNote")}</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {status.enabled ? (
          <>
            <Button variant="secondary" onClick={() => setOpen("codes")}>
              {t("twoStep.newCodes")}
            </Button>
            {!status.required && (
              <Button variant="ghost" onClick={() => setOpen("off")}>
                {t("twoStep.turnOff")}
              </Button>
            )}
          </>
        ) : (
          <Button onClick={() => setOpen("setup")}>{t("twoStep.setUp")}</Button>
        )}
      </div>

      <Dialog open={open === "setup"} onClose={close} title={t("twoStep.setUp")}>
        <TwoStepSetup onDone={close} />
      </Dialog>
      <Dialog open={open === "codes"} onClose={close} title={t("twoStep.newCodes")}>
        {newCodes ? (
          <RecoveryCodes codes={newCodes} onDone={close} />
        ) : (
          <PasswordStep
            intro={t("twoStep.newCodesIntro")}
            submitLabel={t("twoStep.newCodes")}
            onSubmit={async (password) => {
              setNewCodes((await twoStepApi.newRecoveryCodes(password)).recovery_codes);
            }}
          />
        )}
      </Dialog>
      <Dialog open={open === "off"} onClose={close} title={t("twoStep.turnOff")}>
        <PasswordStep
          intro={t("twoStep.turnOffIntro")}
          submitLabel={t("twoStep.turnOff")}
          danger
          onSubmit={async (password) => {
            await twoStepApi.disable(password);
            close();
          }}
        />
      </Dialog>
    </Card>
  );
}
