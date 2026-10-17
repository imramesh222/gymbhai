"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Select, TextArea } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { plural, t } from "@/i18n";
import { branchesApi, errorMessage, membershipsApi, request } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

/**
 * Extend everyone (PLAN.md §5.6): the gym shut for Dashain, every current
 * membership gets the days back. Empty to start; before anything changes it
 * says how many memberships, and that number is typed to confirm.
 */
export function ExtendEveryone({ onClose }: { onClose: () => void }) {
  const confirm = useConfirm();
  const toast = useToast();
  const { data: branches } = useLoad(() => branchesApi.list(), []);
  const [days, setDays] = useState("");
  const [reason, setReason] = useState("");
  const [branchId, setBranchId] = useState("all");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const branch = branchId === "all" ? null : branchId;
    try {
      const { extended } = await request<{ extended: number }>(
        `/api/v1/memberships/extend-all/preview${branch ? `?branch_id=${branch}` : ""}`,
      );
      if (extended === 0) return setError(t("extendAll.nothing"));
      const yes = await confirm({
        title: t("extendAll.title"),
        message: plural(extended, "extendAll.confirmOne", "extendAll.confirm", {
          days,
        }),
        confirmLabel: t("extendAll.submit"),
        danger: true,
        typeToConfirm: String(extended),
      });
      if (!yes) return;
      const result = await membershipsApi.extendAll(Number(days), reason, branch);
      toast.success(plural(result.extended, "extendAll.doneOne", "extendAll.done"));
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("extendAll.title")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <p className="text-sm text-slate-600">{t("extendAll.help")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("membership.days")}
            value={days}
            onChange={setDays}
            type="number"
            inputMode="numeric"
            required
          />
          {branches && branches.length > 1 && (
            <Select
              label={t("sale.branch")}
              value={branchId}
              onChange={setBranchId}
              options={[
                { value: "all", label: t("extendAll.allBranches") },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          )}
        </div>
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("extendAll.continue")}
        </Button>
      </form>
    </Dialog>
  );
}
