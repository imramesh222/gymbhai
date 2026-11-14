"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Checkbox, TextArea } from "@/components/ui/inputs";
import { SmsCounter } from "@/components/ui/SmsCounter";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { errorMessage, messagesApi, type ReminderRule } from "@/lib/api";

import { when, type TriggerInfo } from "./triggers";

function Placeholders({ names }: { names: string[] }) {
  return (
    <p className="text-xs text-slate-500">
      {t("automations.placeholders")}{" "}
      {names.map((name, i) => (
        <span key={name}>
          {i > 0 && " "}
          <code className="rounded bg-slate-100 px-1 text-slate-700">{`{${name}}`}</code>
        </span>
      ))}
    </p>
  );
}

/**
 * What a member who agreed gets on WhatsApp instead of the SMS (PLAN.md
 * §19.3): our wording, approved by Meta, so the gym can't edit it.
 */
export function WhatsAppWording({ text }: { text: string | null | undefined }) {
  if (!text)
    return <p className="text-xs text-slate-500">{t("automations.whatsappNone")}</p>;
  return (
    <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
      <p className="font-semibold">{t("automations.whatsappWording")}</p>
      <p className="mt-0.5">{text}</p>
    </div>
  );
}

function RuleEditor({
  info,
  rule,
  onChanged,
  whatsapp,
}: {
  info: TriggerInfo;
  rule: ReminderRule;
  onChanged: () => void;
  whatsapp: boolean;
}) {
  const toast = useToast();
  const confirm = useConfirm();
  const [template, setTemplate] = useState(rule.template);
  const [days, setDays] = useState(String(rule.days));
  // Ticks at once; goes back if the save fails.
  const [enabled, setEnabled] = useState(rule.enabled);
  const [error, setError] = useState<string | null>(null);
  const hasDays = info.min !== info.max;
  const dirty = template !== rule.template || Number(days) !== rule.days;

  async function save(patch: Partial<ReminderRule>, message: string) {
    setError(null);
    try {
      await messagesApi.updateRule(rule.id, patch);
      toast.success(message);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
      if (patch.enabled !== undefined) setEnabled(!patch.enabled);
    }
  }

  async function remove() {
    const ok = await confirm({
      title: t("automations.delete"),
      message: t("automations.deleteConfirm", { when: when(rule.trigger, rule.days) }),
      confirmLabel: t("automations.delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await messagesApi.deleteRule(rule.id);
      toast.success(t("automations.deleted"));
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="space-y-2 rounded-xl p-3 ring-1 ring-hairline">
      <div className="flex items-center justify-between gap-2">
        <Checkbox
          label={when(rule.trigger, rule.days)}
          hint={enabled ? t("automations.on") : t("automations.off")}
          checked={enabled}
          onChange={(on) => {
            setEnabled(on);
            void save(
              { enabled: on },
              on ? t("automations.turnedOn") : t("automations.turnedOff"),
            );
          }}
        />
        <Button variant="ghost" onClick={() => remove()}>
          <Trash2 className="size-4" aria-hidden />
          <span className="sr-only sm:not-sr-only">{t("automations.delete")}</span>
        </Button>
      </div>
      {hasDays && (
        <div className="max-w-48">
          <Field
            label={t("automations.days")}
            value={days}
            onChange={setDays}
            type="number"
            inputMode="numeric"
          />
        </div>
      )}
      <TextArea
        label={t("automations.wording")}
        value={template}
        onChange={setTemplate}
        rows={3}
      />
      {info.pushOnly ? (
        <p className="text-xs text-slate-500">{t("automations.pushOnly")}</p>
      ) : (
        <SmsCounter text={template} />
      )}
      {whatsapp && !info.pushOnly && <WhatsAppWording text={rule.whatsapp} />}
      {error && <Notice tone="error">{error}</Notice>}
      {dirty && (
        <Button
          variant="secondary"
          onClick={() =>
            save(
              { template, ...(hasDays ? { days: Number(days) } : {}) },
              t("common.saved"),
            )
          }
        >
          {t("common.save")}
        </Button>
      )}
    </div>
  );
}

function AddRule({ info, onAdded }: { info: TriggerInfo; onAdded: () => void }) {
  const toast = useToast();
  const hasDays = info.min !== info.max;
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(String(info.min < 0 ? -1 : info.min));
  const [template, setTemplate] = useState(t(info.example));
  const [error, setError] = useState<string | null>(null);

  if (!open)
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        <Plus className="size-4" aria-hidden />
        {t("automations.add")}
      </Button>
    );

  return (
    <Form
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await messagesApi.createRule({
            trigger: info.trigger,
            days: Number(days),
            template,
            // A new one starts off: the gym turns it on when the wording is right.
            enabled: false,
          });
          toast.success(t("automations.added"));
          setOpen(false);
          onAdded();
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
      className="space-y-2 rounded-xl border border-dashed border-slate-300 p-3"
    >
      <h3 className="text-sm font-semibold">{t("automations.add")}</h3>
      {hasDays && (
        <div className="max-w-48">
          <Field
            label={t("automations.days")}
            value={days}
            onChange={setDays}
            type="number"
            inputMode="numeric"
            help={when(info.trigger, Number(days) || 0)}
          />
        </div>
      )}
      <TextArea
        label={t("automations.wording")}
        value={template}
        onChange={setTemplate}
        rows={3}
        required
      />
      {info.pushOnly ? (
        <p className="text-xs text-slate-500">{t("automations.pushOnly")}</p>
      ) : (
        <SmsCounter text={template} />
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button type="submit" variant="secondary">
          {t("common.add")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    </Form>
  );
}

/** One trigger's automations: e.g. every "before it ends" reminder. */
export function TriggerCard({
  info,
  rules,
  onChanged,
  whatsapp = false,
}: {
  info: TriggerInfo;
  rules: ReminderRule[];
  onChanged: () => void;
  /** The gym sends WhatsApp messages (§19.3): show each rule's wording. */
  whatsapp?: boolean;
}) {
  const hasDays = info.min !== info.max;
  return (
    <Card title={t(info.title)}>
      <div className="space-y-3">
        <p className="text-sm text-slate-600">{t(info.help)}</p>
        {rules.map((rule) => (
          <RuleEditor
            key={rule.id}
            info={info}
            rule={rule}
            onChanged={onChanged}
            whatsapp={whatsapp}
          />
        ))}
        <Placeholders names={info.placeholders} />
        {(hasDays || rules.length === 0) && <AddRule info={info} onAdded={onChanged} />}
      </div>
    </Card>
  );
}
