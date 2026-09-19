"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { TextArea } from "@/components/ui/inputs";
import { SmsCounter } from "@/components/ui/SmsCounter";
import { t } from "@/i18n";
import { errorMessage, messagesApi } from "@/lib/api";

export function SendSms({
  memberId,
  onClose,
  onSent,
}: {
  memberId: string;
  onClose: () => void;
  onSent: () => void;
}) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send(payload: { reminder?: boolean; body?: string }) {
    setError(null);
    try {
      await messagesApi.smsMember(memberId, payload);
      onSent();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("sms.send")}>
      <div className="space-y-3">
        <Button variant="secondary" block onClick={() => void send({ reminder: true })}>
          {t("expiring.remind")}
        </Button>
        <p className="text-center text-xs text-slate-500">{t("sms.or")}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send({ body });
          }}
          className="space-y-2"
        >
          <TextArea
            label={t("sms.message")}
            value={body}
            onChange={setBody}
            rows={3}
            required
          />
          <SmsCounter text={body} />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" block>
            {t("sms.send")}
          </Button>
        </form>
      </div>
    </Dialog>
  );
}
