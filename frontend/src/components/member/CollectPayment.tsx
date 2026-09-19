"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import {
  PaymentFields,
  toPaymentInput,
  type PaymentDraft,
} from "@/components/money/PaymentFields";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage, paymentsApi, type Membership, type Payment } from "@/lib/api";
import { formatRs } from "@/lib/money";

/** Take money towards a membership's dues (part payments are normal). */
export function CollectPayment({
  memberships,
  open,
  onClose,
  onDone,
}: {
  memberships: Membership[];
  open: boolean;
  onClose: () => void;
  onDone: (payment: Payment) => void;
}) {
  const owing = memberships.filter((m) => m.dues > 0);
  const [membershipId, setMembershipId] = useState(owing[0]?.id ?? "");
  const chosen = owing.find((m) => m.id === membershipId) ?? owing[0];
  const [draft, setDraft] = useState<PaymentDraft>({
    amount: chosen?.dues ?? null,
    method: "cash",
    transactionRef: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const payment = toPaymentInput(draft);
    if (!chosen || !payment) return;
    setPending(true);
    setError(null);
    try {
      onDone(await paymentsApi.collect(chosen.id, payment));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("payment.collect")}>
      {owing.length === 0 ? (
        <p className="text-sm text-slate-600">{t("payment.nothingOwed")}</p>
      ) : (
        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          {owing.length > 1 && (
            <Select
              label={t("payment.forMembership")}
              value={chosen?.id ?? ""}
              onChange={(id) => {
                setMembershipId(id);
                const m = owing.find((x) => x.id === id);
                setDraft({ ...draft, amount: m?.dues ?? null });
              }}
              options={owing.map((m) => ({
                value: m.id,
                label: `${m.plan_name} — ${t("payment.owes", { amount: formatRs(m.dues) })}`,
              }))}
            />
          )}
          <PaymentFields value={draft} onChange={setDraft} owed={chosen?.dues} />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" block disabled={pending || !draft.amount}>
            {pending ? t("common.saving") : t("payment.record")}
          </Button>
        </form>
      )}
    </Dialog>
  );
}
