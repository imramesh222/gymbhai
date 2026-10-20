"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { Checkbox, TextArea } from "@/components/ui/inputs";
import { SmsCounter } from "@/components/ui/SmsCounter";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { errorMessage, messagesApi } from "@/lib/api";

import { WhatsAppWording } from "./Automations";

type Templates = {
  welcome_sms: string;
  membership_sms: string;
  whatsapp?: boolean;
  welcome_whatsapp?: string;
  membership_whatsapp?: string;
};

/** Push first, SMS for the rest; or SMS to everyone as well (§16.3, 8.3). */
export function HowMessagesGo({ initial }: { initial: boolean }) {
  const toast = useToast();
  const [alsoSms, setAlsoSms] = useState(initial);
  return (
    <Card title={t("automations.how.title")}>
      <p className="text-sm text-slate-600">{t("automations.how.help")}</p>
      <div className="mt-2">
        <Checkbox
          label={t("automations.how.alsoSms")}
          hint={t("automations.how.alsoSmsHint")}
          checked={alsoSms}
          onChange={async (on) => {
            setAlsoSms(on);
            try {
              await messagesApi.updateTemplates({ also_sms: on });
              toast.success(t("common.saved"));
            } catch (err) {
              setAlsoSms(!on);
              toast.error(errorMessage(err));
            }
          }}
        />
      </div>
    </Card>
  );
}

/** The SMS sent at the desk: on adding a member, and on every sale (§5.3). */
export function DeskSms({ initial }: { initial: Templates }) {
  const toast = useToast();
  const [form, setForm] = useState({
    welcome_sms: initial.welcome_sms,
    membership_sms: initial.membership_sms,
  });
  const [error, setError] = useState<string | null>(null);
  return (
    <Card title={t("automations.deskSms")}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await messagesApi.updateTemplates(form);
            toast.success(t("common.saved"));
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
        className="space-y-3"
      >
        <div>
          <TextArea
            label={t("automations.welcome")}
            value={form.welcome_sms}
            onChange={(welcome_sms) => setForm({ ...form, welcome_sms })}
            rows={3}
          />
          <SmsCounter text={form.welcome_sms} />
          {initial.whatsapp && <WhatsAppWording text={initial.welcome_whatsapp} />}
        </div>
        <div>
          <TextArea
            label={t("automations.membership")}
            value={form.membership_sms}
            onChange={(membership_sms) => setForm({ ...form, membership_sms })}
            rows={3}
          />
          <SmsCounter text={form.membership_sms} />
          {initial.whatsapp && <WhatsAppWording text={initial.membership_whatsapp} />}
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="secondary">
          {t("common.save")}
        </Button>
      </form>
    </Card>
  );
}
