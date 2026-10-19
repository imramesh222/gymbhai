"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, TextArea } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage, ptApi, type PtPackage, type PtPackageDetail } from "@/lib/api";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useIdempotencyKey } from "@/lib/idempotency";

/**
 * One session trained (PLAN.md §18.3): today unless changed, with a note for
 * staff. Recorded once, however often it's tapped on a weak connection.
 */
export function RecordSession({
  pkg,
  onClose,
  onRecorded,
}: {
  pkg: PtPackage;
  onClose: () => void;
  onRecorded: (updated: PtPackageDetail) => void;
}) {
  const { display } = useGymCalendar();
  const [trainedOn, setTrainedOn] = useState(todayInNepal());
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const saving = useIdempotencyKey();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = { trained_on: trainedOn, note: note.trim() || null };
    setPending(true);
    setError(null);
    try {
      const updated = await ptApi.record(pkg.id, body, saving.keyFor(body));
      saving.succeeded();
      onRecorded(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("pt.recordTitle")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <p className="text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{pkg.member_name}</span> ·{" "}
          {pkg.plan_name}
        </p>
        <DateInput
          label={t("pt.trainedOn")}
          value={trainedOn}
          onChange={setTrainedOn}
          display={display}
          required
        />
        <div>
          <TextArea label={t("pt.note")} value={note} onChange={setNote} rows={2} />
          <p className="mt-1.5 text-sm text-slate-500">{t("pt.noteHelp")}</p>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {pending ? t("common.saving") : t("pt.record")}
        </Button>
      </form>
    </Dialog>
  );
}
