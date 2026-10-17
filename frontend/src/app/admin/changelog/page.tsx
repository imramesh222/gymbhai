"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Checkbox, TextArea } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { adminApi, errorMessage, type ChangelogEntry } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

function Editor({
  entry,
  onSaved,
}: {
  entry: ChangelogEntry | null;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [title, setTitle] = useState(entry?.title ?? "");
  const [body, setBody] = useState(entry?.body ?? "");
  const [publish, setPublish] = useState(Boolean(entry?.published_at));
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        const published_at = publish
          ? (entry?.published_at ?? new Date().toISOString())
          : null;
        try {
          if (entry)
            await adminApi.editChangelog(entry.id, { title, body, published_at });
          else await adminApi.addChangelog({ title, body, published_at });
          toast.success(t("common.saved"));
          if (!entry) {
            setTitle("");
            setBody("");
            setPublish(false);
          }
          onSaved();
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <Field
        label={t("changelog.titleField")}
        value={title}
        onChange={setTitle}
        required
      />
      <TextArea
        label={t("changelog.body")}
        value={body}
        onChange={setBody}
        rows={4}
        required
      />
      <Checkbox
        label={t("changelog.publish")}
        hint={t("changelog.publishHelp")}
        checked={publish}
        onChange={setPublish}
      />
      {error && <Notice tone="error">{error}</Notice>}
      <Button type="submit">{t("common.save")}</Button>
    </form>
  );
}

/** What's new in GymBhai, written here (PLAN.md §16.5, 10.4). */
export default function AdminChangelogPage() {
  const confirm = useConfirm();
  const { data, reload } = useLoad(() => adminApi.changelog(), []);
  return (
    <div className="space-y-4">
      <PageHeader title={t("changelog.title")} subtitle={t("changelog.adminHelp")} />
      <Card title={t("changelog.new")}>
        <Editor entry={null} onSaved={reload} />
      </Card>
      {data?.map((entry) => (
        <Card
          key={entry.id + (entry.published_at ?? "")}
          title={
            entry.published_at
              ? `${entry.title} · ${formatDateTime(entry.published_at, "ad")}`
              : `${entry.title} · ${t("changelog.draft")}`
          }
          actions={
            <Button
              variant="ghost"
              onClick={async () => {
                const ok = await confirm({
                  title: t("changelog.delete"),
                  message: t("changelog.deleteConfirm", { title: entry.title }),
                  confirmLabel: t("changelog.delete"),
                  danger: true,
                });
                if (ok) {
                  await adminApi.deleteChangelog(entry.id);
                  reload();
                }
              }}
            >
              {t("changelog.delete")}
            </Button>
          }
        >
          <Editor entry={entry} onSaved={reload} />
        </Card>
      ))}
    </div>
  );
}
