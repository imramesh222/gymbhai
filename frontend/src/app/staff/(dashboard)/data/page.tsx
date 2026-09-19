"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, reportsApi, type ImportPreview } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const EXPORTS = ["members", "memberships", "payments", "check-ins"] as const;
const FIELDS = [
  "name",
  "phone",
  "email",
  "gender",
  "joined_on",
  "plan_name",
  "start_date",
  "end_date",
  "notes",
];

/** Import an existing register, and download everything (§7 Import / Export). */
export default function DataPage() {
  const { can } = useAuth();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, number | null>>({});
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const canImport = can("members.add") && can("memberships.sell");

  async function run(action: () => Promise<void>) {
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("data.title")} />
      <Card title={t("data.export")}>
        <p className="mb-3 text-sm text-slate-600">{t("data.exportHelp")}</p>
        <div className="flex flex-wrap gap-2">
          {EXPORTS.filter((kind) => kind !== "payments" || can("reports.money")).map(
            (kind) => (
              <Button
                key={kind}
                variant="secondary"
                onClick={() => run(() => reportsApi.download(kind))}
              >
                {t(`data.export.${kind}` as MessageKey)}
              </Button>
            ),
          )}
        </div>
      </Card>

      {canImport && (
        <Card title={t("data.import")}>
          <p className="mb-3 text-sm text-slate-600">{t("data.importHelp")}</p>
          {!preview || preview.status === "committed" ? (
            <input
              type="file"
              accept=".xlsx,.csv"
              aria-label={t("data.chooseFile")}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file)
                  void run(async () => {
                    const result = await reportsApi.uploadRegister(file);
                    setPreview(result);
                    setMapping(result.mapping);
                  });
              }}
            />
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-medium">
                {t("data.rows", { total: preview.total_rows, ready: preview.ready })}
              </p>
              <div className="grid gap-2 sm:grid-cols-3">
                {FIELDS.map((field) => (
                  <label key={field} className="text-sm">
                    {t(`data.field.${field}` as MessageKey)}
                    <select
                      value={mapping[field] ?? ""}
                      onChange={(e) =>
                        setMapping({
                          ...mapping,
                          [field]:
                            e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                      className="mt-1 block w-full rounded border border-slate-300 px-2 py-1.5"
                    >
                      <option value="">{t("data.notInFile")}</option>
                      {preview.headers.map((header, i) => (
                        <option key={i} value={i}>
                          {header}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <Button
                variant="secondary"
                onClick={() =>
                  run(async () =>
                    setPreview(await reportsApi.previewRegister(preview.id, mapping)),
                  )
                }
              >
                {t("data.check")}
              </Button>
              {preview.problems.length > 0 && (
                <Notice tone="warning">
                  <p className="font-medium">{t("data.problems")}</p>
                  <ul className="mt-1 list-disc pl-5">
                    {preview.problems.slice(0, 15).map(([row, problem]) => (
                      <li key={row}>{t("data.problem", { row, problem })}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              <div className="overflow-x-auto">
                <table className="text-xs">
                  <thead>
                    <tr>
                      {preview.headers.map((h, i) => (
                        <th key={i} className="border-b px-2 py-1 text-left">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.slice(0, 8).map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, c) => (
                          <td key={c} className="border-b px-2 py-1">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button
                onClick={() =>
                  window.confirm(t("data.commitConfirm", { count: preview.ready })) &&
                  run(async () => {
                    const done = await reportsApi.commitRegister(preview.id, mapping);
                    setPreview(done);
                    setMessage({
                      tone: "success",
                      text: t("data.imported", {
                        created: done.result?.created ?? 0,
                        skipped: done.result?.skipped ?? 0,
                      }),
                    });
                  })
                }
              >
                {t("data.commit", { count: preview.ready })}
              </Button>
            </div>
          )}
        </Card>
      )}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
    </div>
  );
}
