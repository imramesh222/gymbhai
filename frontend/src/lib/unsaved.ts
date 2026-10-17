"use client";

import { useEffect } from "react";

/**
 * While a form has changes that aren't saved, leaving the page (reload, close
 * the tab, type another address) asks first (PLAN.md §16.2, 7.8).
 */
export function useUnsavedWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}
