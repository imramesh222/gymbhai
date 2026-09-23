"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { Checkbox, TextArea } from "@/components/ui/inputs";
import { SmsCounter } from "@/components/ui/SmsCounter";
import { t } from "@/i18n";
import { errorMessage, messagesApi, type ReminderRule } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

function when(days: number): string {
  if (days === 0) return t("reminders.onTheDay");
  return days < 0
    ? t("reminders.before", { count: -days })
    : t("reminders.after", { count: days });
}

/** Reminder rules and the wording of every SMS the gym sends (§9, §10). */
export function RemindersSection() {
  const rules = useLoad(() => messagesApi.rules(), []);
  const templates = useLoad(() => messagesApi.templates(), []);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setSaved(false);
    try {
      await action();
      setSaved(true);
      rules.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card title={t("reminders.title")}>
      <p className="mb-3 text-sm text-slate-600">{t("reminders.help")}</p>
      <div className="space-y-4">
        {rules.data?.map((rule) => (
          <RuleEditor
            key={rule.id}
            rule={rule}
            onSave={(patch) => run(() => messagesApi.updateRule(rule.id, patch))}
            onDelete={() => run(() => messagesApi.deleteRule(rule.id))}
          />
        ))}
      </div>
      <AddRule
        onAdd={(days, template) =>
          run(() =>
            messagesApi.createRule({ days_from_expiry: days, template, enabled: true }),
          )
        }
      />
      {templates.data && (
        <TemplatesEditor
          initial={templates.data}
          onSave={(body) => run(() => messagesApi.updateTemplates(body))}
        />
      )}
      <p className="mt-3 text-xs text-slate-500">{t("reminders.placeholders")}</p>
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {saved && (
        <div className="mt-2">
          <Notice tone="success">{t("common.saved")}</Notice>
        </div>
      )}
    </Card>
  );
}

function RuleEditor({
  rule,
  onSave,
  onDelete,
}: {
  rule: ReminderRule;
  onSave: (patch: Partial<ReminderRule>) => void;
  onDelete: () => void;
}) {
  const [template, setTemplate] = useState(rule.template);
  return (
    <div className="rounded-xl p-3 ring-1 ring-hairline">
      <div className="flex items-center justify-between">
        <Checkbox
          label={when(rule.days_from_expiry)}
          checked={rule.enabled}
          onChange={(enabled) => onSave({ enabled })}
        />
        <Button variant="ghost" onClick={onDelete}>
          {t("reminders.delete")}
        </Button>
      </div>
      <TextArea
        label={t("reminders.wording")}
        value={template}
        onChange={setTemplate}
        rows={3}
      />
      <SmsCounter text={template} />
      {template !== rule.template && (
        <Button
          variant="secondary"
          className="mt-2"
          onClick={() => onSave({ template })}
        >
          {t("common.save")}
        </Button>
      )}
    </div>
  );
}

function AddRule({ onAdd }: { onAdd: (days: number, template: string) => void }) {
  const [days, setDays] = useState("-1");
  const [template, setTemplate] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onAdd(Number(days), template);
        setTemplate("");
      }}
      className="mt-4 space-y-2 rounded-lg border border-dashed border-slate-300 p-3"
    >
      <h3 className="text-sm font-semibold">{t("reminders.add")}</h3>
      <label className="block text-sm">
        {t("reminders.daysField")}
        <input
          type="number"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="ml-2 w-20 rounded-lg bg-white px-2 py-1 ring-1 ring-hairline outline-none transition focus:ring-2 focus:ring-brand-500"
        />
        <span className="ml-2 text-slate-500">{when(Number(days) || 0)}</span>
      </label>
      <TextArea
        label={t("reminders.wording")}
        value={template}
        onChange={setTemplate}
        required
      />
      <SmsCounter text={template} />
      <Button type="submit" variant="secondary">
        {t("common.add")}
      </Button>
    </form>
  );
}

function TemplatesEditor({
  initial,
  onSave,
}: {
  initial: { welcome_sms: string; membership_sms: string };
  onSave: (body: { welcome_sms: string; membership_sms: string }) => void;
}) {
  const [form, setForm] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(form);
      }}
      className="mt-6 space-y-3"
    >
      <h3 className="text-sm font-semibold">{t("reminders.deskSms")}</h3>
      <div>
        <TextArea
          label={t("reminders.welcome")}
          value={form.welcome_sms}
          onChange={(welcome_sms) => setForm({ ...form, welcome_sms })}
          rows={3}
        />
        <SmsCounter text={form.welcome_sms} />
      </div>
      <div>
        <TextArea
          label={t("reminders.membership")}
          value={form.membership_sms}
          onChange={(membership_sms) => setForm({ ...form, membership_sms })}
          rows={3}
        />
        <SmsCounter text={form.membership_sms} />
      </div>
      <Button type="submit" variant="secondary">
        {t("common.save")}
      </Button>
    </form>
  );
}
