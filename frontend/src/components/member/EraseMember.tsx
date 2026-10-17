"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { t } from "@/i18n";
import { errorMessage, membersApi, type MemberDetail } from "@/lib/api";

/**
 * Erase member (PLAN.md §16.1): the owner removes a member's personal details
 * for good, at the member's request. Typing their name is the confirmation:
 * there is no undo.
 */
export function EraseMember({
  member,
  onClose,
  onErased,
}: {
  member: MemberDetail;
  onClose: () => void;
  onErased: (erased: MemberDetail) => void;
}) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const matches = typed.trim().toLowerCase() === member.name.trim().toLowerCase();

  return (
    <Dialog open onClose={onClose} title={t("erase.title", { name: member.name })}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!matches) return;
          setPending(true);
          setError(null);
          try {
            onErased(await membersApi.erase(member.id));
          } catch (err) {
            setError(errorMessage(err));
            setPending(false);
          }
        }}
        className="space-y-4"
      >
        <Notice tone="warning">{t("erase.warning")}</Notice>
        <div className="text-sm text-slate-700">
          <p className="font-medium">{t("erase.goes")}</p>
          <p className="mt-1">{t("erase.goesList")}</p>
          <p className="mt-3 font-medium">{t("erase.stays")}</p>
          <p className="mt-1">{t("erase.staysList")}</p>
        </div>
        <Field
          label={t("erase.typeName", { name: member.name })}
          value={typed}
          onChange={setTyped}
          autoComplete="off"
          name="confirm-name"
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block disabled={!matches || pending}>
          {t("erase.submit")}
        </Button>
      </form>
    </Dialog>
  );
}
