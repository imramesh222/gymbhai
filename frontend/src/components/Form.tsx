"use client";

import { createContext, useContext } from "react";

import { useOnce } from "@/lib/useOnce";

const Busy = createContext(false);

/** True while the form around a submit button is sending (Button reads it). */
export function useFormBusy(): boolean {
  return useContext(Busy);
}

/**
 * A <form> that sends once: while the promise `onSubmit` returns is running,
 * Enter and its submit buttons do nothing (lib/useOnce.ts). It calls
 * preventDefault itself.
 */
export function Form({
  onSubmit,
  children,
  ...props
}: Omit<React.FormHTMLAttributes<HTMLFormElement>, "onSubmit"> & {
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => unknown;
}) {
  const { busy, run } = useOnce();
  return (
    <form
      {...props}
      aria-busy={busy || undefined}
      onSubmit={(event) => {
        event.preventDefault();
        run(() => onSubmit(event));
      }}
    >
      <Busy.Provider value={busy}>{children}</Busy.Provider>
    </form>
  );
}
