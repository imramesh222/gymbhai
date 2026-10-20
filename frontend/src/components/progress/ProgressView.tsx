"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { LineChart } from "@/components/charts/LineChart";
import { Card, EmptyState } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { bmi, changes, MEASURES, shown, stored, type Measure } from "@shared/progress";
import type { Progress, ProgressEntry, ProgressInput } from "@shared/types";
import { errorMessage } from "@/lib/api";
import type { DateDisplay } from "@/lib/dates";
import { formatShort, todayInNepal } from "@/lib/dates";

const signed = (value: number, unit: string) =>
  `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value)} ${unit}`;

/** "62.5 kg · Waist 76 cm": what a check measured, in a line. */
export function entryLine(entry: ProgressEntry): string {
  return MEASURES.filter((m) => entry[m.key] !== null)
    .map((m) =>
      m.key === "weight_g"
        ? `${shown(entry.weight_g, "kg")} kg`
        : `${t(m.label).replace(/ \(.*\)$/, "")} ${shown(entry[m.key], m.unit)} ${m.unit}`,
    )
    .join(" · ");
}

/**
 * Progress (PLAN.md §19.5): the latest weight and its change, BMI, the weight
 * over time, and every check. Shared by the member's app and the staff
 * profile; who may change which check is the caller's to say.
 */
export function ProgressView({
  progress,
  display,
  date,
  mayChange,
  onSave,
  onDelete,
  onHeight,
}: {
  progress: Progress;
  display: DateDisplay;
  date: (iso: string) => string;
  mayChange: (entry: ProgressEntry) => boolean;
  onSave: (input: ProgressInput, entry: ProgressEntry | null) => Promise<void>;
  onDelete: (entry: ProgressEntry) => Promise<void>;
  onHeight: (heightMm: number | null) => Promise<void>;
}) {
  const confirm = useConfirm();
  const [editing, setEditing] = useState<ProgressEntry | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const weight = changes(progress.entries, "weight_g");
  const latestBmi = bmi(weight?.latest ?? null, progress.height_mm);
  // Oldest first, for the chart: one point a check that has a weight.
  const weights = [...progress.entries]
    .filter((e) => e.weight_g !== null)
    .sort((a, b) => a.measured_on.localeCompare(b.measured_on));

  return (
    <div className="space-y-4">
      <Card
        title={t("progress.title")}
        actions={<Button onClick={() => setEditing("new")}>{t("progress.add")}</Button>}
      >
        {error && <Notice tone="error">{error}</Notice>}
        {weight ? (
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className="text-3xl font-semibold tabular-nums text-slate-900">
              {shown(weight.latest, "kg")} kg
            </p>
            {weight.sinceFirst !== null && (
              <p className="text-sm text-slate-600">
                {t("progress.sinceFirst", {
                  change: signed(shown(weight.sinceFirst, "kg")!, "kg"),
                })}
              </p>
            )}
            {weight.sinceLast !== null && (
              <p className="text-sm text-slate-600">
                {t("progress.sinceLast", {
                  change: signed(shown(weight.sinceLast, "kg")!, "kg"),
                })}
              </p>
            )}
            {latestBmi !== null && (
              <p className="text-sm text-slate-600">
                {t("progress.bmi", { value: latestBmi })}
              </p>
            )}
          </div>
        ) : null}
        <Height value={progress.height_mm} onSave={onHeight} />
      </Card>

      {weights.length >= 2 && (
        // The card names the one series: no legend needed.
        <Card title={t("progress.weightChart")}>
          <LineChart
            title={t("progress.weightChart")}
            fit
            labels={weights.map((e) => formatShort(e.measured_on, display))}
            series={[
              {
                key: "weight",
                label: t("progress.weightChart"),
                values: weights.map((e) => shown(e.weight_g, "kg")),
              },
            ]}
            format={(value) => `${value} kg`}
            tickFormat={(value) => String(value)}
          />
        </Card>
      )}

      <Card>
        {progress.entries.length === 0 ? (
          <EmptyState title={t("progress.none")} />
        ) : (
          <ul className="divide-y divide-hairline">
            {progress.entries.map((entry) => (
              <li
                key={entry.id}
                className="flex items-start justify-between gap-3 py-2.5"
              >
                <div className="min-w-0 text-sm">
                  <p className="font-medium text-slate-900">
                    {date(entry.measured_on)}
                  </p>
                  <p className="text-slate-700">{entryLine(entry)}</p>
                  {entry.note && <p className="text-xs text-slate-500">{entry.note}</p>}
                  {entry.recorded_by_name && (
                    <p className="text-xs text-slate-500">
                      {t("progress.by", { name: entry.recorded_by_name })}
                    </p>
                  )}
                </div>
                {mayChange(entry) ? (
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(entry)}>
                      {t("common.edit")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={async () => {
                        if (
                          !(await confirm({
                            title: t("progress.delete"),
                            message: t("progress.deleteConfirm"),
                            confirmLabel: t("progress.delete"),
                            danger: true,
                          }))
                        )
                          return;
                        try {
                          await onDelete(entry);
                        } catch (err) {
                          setError(errorMessage(err));
                        }
                      }}
                    >
                      {t("progress.delete")}
                    </Button>
                  </div>
                ) : (
                  <span className="shrink-0 text-xs text-slate-400">
                    {t("progress.membersOwn")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {editing && (
        <EntryDialog
          entry={editing === "new" ? null : editing}
          display={display}
          onClose={() => setEditing(null)}
          onSave={async (input) => {
            await onSave(input, editing === "new" ? null : editing);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function Height({
  value,
  onSave,
}: {
  value: number | null;
  onSave: (heightMm: number | null) => Promise<void>;
}) {
  const [text, setText] = useState(value ? String(value / 10) : "");
  const [error, setError] = useState<string | null>(null);
  const changed = (stored(text, "cm") ?? null) !== value;
  return (
    <div className="mt-3 flex flex-wrap items-end gap-2">
      <div className="w-40">
        <Field
          label={t("progress.height")}
          value={text}
          onChange={setText}
          inputMode="decimal"
          help={t("progress.heightHelp")}
        />
      </div>
      {changed && (
        <Button
          variant="secondary"
          size="sm"
          onClick={async () => {
            try {
              await onSave(stored(text, "cm"));
              setError(null);
            } catch (err) {
              setError(errorMessage(err));
            }
          }}
        >
          {t("common.save")}
        </Button>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

function EntryDialog({
  entry,
  display,
  onClose,
  onSave,
}: {
  entry: ProgressEntry | null;
  display: DateDisplay;
  onClose: () => void;
  onSave: (input: ProgressInput) => Promise<void>;
}) {
  const [day, setDay] = useState(entry?.measured_on ?? todayInNepal());
  const [values, setValues] = useState<Record<Measure, string>>(
    () =>
      Object.fromEntries(
        MEASURES.map((m) => {
          const value = entry ? shown(entry[m.key], m.unit) : null;
          return [m.key, value === null ? "" : String(value)];
        }),
      ) as Record<Measure, string>,
  );
  const [note, setNote] = useState(entry?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const input: ProgressInput = { measured_on: day, note: note.trim() || null };
    for (const m of MEASURES) input[m.key] = stored(values[m.key], m.unit);
    if (MEASURES.every((m) => input[m.key] === null))
      return setError(t("progress.needOne"));
    setPending(true);
    setError(null);
    try {
      await onSave(input);
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={entry ? t("progress.edit") : t("progress.add")}
    >
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <DateInput
          label={t("progress.date")}
          value={day}
          onChange={setDay}
          display={display}
        />
        <div className="grid grid-cols-2 gap-3">
          {MEASURES.map((m) => (
            <Field
              key={m.key}
              label={t(m.label)}
              value={values[m.key]}
              onChange={(value) => setValues({ ...values, [m.key]: value })}
              inputMode="decimal"
            />
          ))}
        </div>
        <Field label={t("progress.note")} value={note} onChange={setNote} />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {pending ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
