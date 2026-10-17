"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Dialog } from "@/components/ui/Dialog";
import { t } from "@/i18n";

export interface ConfirmOptions {
  title: string;
  /** What will happen, in plain words: "Adds 7 days to 214 memberships." */
  message: React.ReactNode;
  confirmLabel: string;
  /** Red for anything that removes, cancels or can't be undone. */
  danger?: boolean;
  /** For what can't be undone: the person types this to enable the button. */
  typeToConfirm?: string;
}

type Ask = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Ask | null>(null);

function ConfirmView({
  options,
  onAnswer,
}: {
  options: ConfirmOptions;
  onAnswer: (yes: boolean) => void;
}) {
  const [typed, setTyped] = useState("");
  const needed = options.typeToConfirm;
  const ready = !needed || typed.trim().toLowerCase() === needed.trim().toLowerCase();
  return (
    <Dialog open onClose={() => onAnswer(false)} title={options.title}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) onAnswer(true);
        }}
        className="space-y-4"
      >
        <div className="text-sm text-slate-700">{options.message}</div>
        {needed && (
          <Field
            label={t("confirm.typeToConfirm", { text: needed })}
            value={typed}
            onChange={setTyped}
            autoComplete="off"
            name="confirm-text"
          />
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={() => onAnswer(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            variant={options.danger ? "danger" : "primary"}
            disabled={!ready}
          >
            {options.confirmLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/**
 * One confirmation dialog for the whole app, in place of window.confirm:
 *
 *     const confirm = useConfirm();
 *     if (!(await confirm({ title, message, confirmLabel, danger: true }))) return;
 */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolve = useRef<((yes: boolean) => void) | null>(null);
  const ask = useCallback<Ask>(
    (next) =>
      new Promise<boolean>((done) => {
        resolve.current?.(false);
        resolve.current = done;
        setOptions(next);
      }),
    [],
  );
  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {options && (
        <ConfirmView
          key={options.title}
          options={options}
          onAnswer={(yes) => {
            resolve.current?.(yes);
            resolve.current = null;
            setOptions(null);
          }}
        />
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext);
  if (!ask) throw new Error("useConfirm must be used inside ConfirmProvider");
  return ask;
}
