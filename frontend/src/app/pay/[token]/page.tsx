"use client";

import { use, useState } from "react";

import { Expired, Loading, OpenCheckout, Outcome } from "@/components/pay/Checkout";
import { memberApi } from "@/lib/memberApi";
import { useLoad } from "@/lib/useLoad";
import type { PayPage } from "@shared/types";

/**
 * A payment through the gym's own merchant account (PLAN.md §20.2), by its
 * signed link: the phone app opens it in the phone's browser, which has no
 * member session.
 */
export default function PayScreen({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const loaded = useLoad(() => memberApi.payPage(token), [token]);
  const [page, setPage] = useState<PayPage | null>(null);
  const [checking, setChecking] = useState(false);
  const shown = page ?? loaded.data;

  async function check() {
    setChecking(true);
    try {
      setPage(await memberApi.payCheck(token));
    } catch {
      // The page still shows what it knew; "Check again" stays.
    } finally {
      setChecking(false);
    }
  }

  if (loaded.error) return <Expired />;
  if (!shown) return <Loading />;
  if (shown.status === "started" && shown.checkout)
    return <OpenCheckout token={token} page={shown} onChange={setPage} />;
  return <Outcome page={shown} onCheck={() => void check()} checking={checking} />;
}
