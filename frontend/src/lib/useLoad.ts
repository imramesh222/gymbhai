"use client";

import { useCallback, useEffect, useState } from "react";

import { errorMessage } from "./api";

interface Loaded<T> {
  key: string;
  version: number;
  data: T | null;
  error: string | null;
}

/**
 * Load something from the API when the component mounts or `deps` change;
 * `reload()` fetches again after an edit. The last data stays on screen while
 * a reload is in flight, so pages don't flash empty.
 *
 * "Loading" is derived — the stored result belongs to an older request — rather
 * than set in the effect, which would render twice for every load.
 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const key = JSON.stringify(deps);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<Loaded<T>>({
    key: "",
    version: -1,
    data: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ key, version, data, error: null });
      },
      (err) => {
        if (!cancelled)
          setState((s) => ({ key, version, data: s.data, error: errorMessage(err) }));
      },
    );
    return () => {
      cancelled = true;
    };
    // `load` is a new function every render; `deps` (as `key`) say when it matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data })), []);
  return {
    data: state.data,
    error: state.error,
    loading: state.key !== key || state.version !== version,
    reload,
    setData,
  };
}
