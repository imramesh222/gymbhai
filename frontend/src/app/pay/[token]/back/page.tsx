"use client";

import { use, useCallback, useEffect, useState } from "react";

import { Expired, Loading, Outcome } from "@/components/pay/Checkout";
import { memberApi } from "@/lib/memberApi";
import type { PayPage } from "@shared/types";

// The wallet can take a moment to settle: asked again a few times.
const TRIES = 4;
const APART_MS = 3000;

/**
 * Back from the wallet (PLAN.md §20.2), paid or cancelled. Whatever the
 * wallet put in the address is ignored: the server asks the wallet itself.
 */
export default function PayBack({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [page, setPage] = useState<PayPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [checking, setChecking] = useState(true);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const next = await memberApi.payCheck(token);
      setPage(next);
      return next;
    } catch {
      setFailed(true);
      return null;
    } finally {
      setChecking(false);
    }
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (let i = 0; i < TRIES && !cancelled; i++) {
        const next = await check();
        if (!next || next.status !== "started") return;
        await new Promise((resolve) => setTimeout(resolve, APART_MS));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [check]);

  if (failed && !page) return <Expired />;
  if (!page) return <Loading />;
  return <Outcome page={page} onCheck={() => void check()} checking={checking} />;
}
