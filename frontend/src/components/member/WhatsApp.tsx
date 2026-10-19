"use client";

import { MessageCircle } from "lucide-react";
import { useState } from "react";

import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { Select, TextArea } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import { MESSAGE_PURPOSES, messagesApi, type MessagePurpose } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { whatsappLink } from "@/lib/whatsapp";

/**
 * A WhatsApp message from the desk's own phone (PLAN.md §18.5): the gym's
 * own wording for this member, filled in and editable. WhatsApp opens with
 * it, and goes when someone presses Send there: free, no SMS credit used.
 */
export function WhatsAppDialog({
  memberId,
  purpose: first,
  onClose,
}: {
  memberId: string;
  purpose: MessagePurpose;
  onClose: () => void;
}) {
  const [purpose, setPurpose] = useState<MessagePurpose>(first);
  const { data, error } = useLoad(
    () => messagesApi.memberMessage(memberId, purpose),
    [memberId, purpose],
  );
  return (
    <Dialog open onClose={onClose} title={t("whatsapp.title")}>
      <div className="space-y-3">
        <Select<MessagePurpose>
          label={t("whatsapp.about")}
          value={purpose}
          onChange={setPurpose}
          options={MESSAGE_PURPOSES.map((p) => ({
            value: p,
            label: t(`whatsapp.purpose.${p}` as MessageKey),
          }))}
        />
        {error && <Notice tone="error">{error}</Notice>}
        {/* Keyed by the wording: a new one replaces what was typed. */}
        {data && (
          <Composer
            key={data.text}
            text={data.text}
            phone={data.phone}
            onSent={onClose}
          />
        )}
      </div>
    </Dialog>
  );
}

function Composer({
  text: first,
  phone,
  onSent,
}: {
  text: string;
  phone: string;
  onSent: () => void;
}) {
  const [text, setText] = useState(first);
  return (
    <>
      <TextArea
        label={t("whatsapp.message")}
        value={text}
        onChange={setText}
        rows={5}
      />
      <p className="text-xs text-slate-500">{t("whatsapp.help", { phone })}</p>
      <a
        href={whatsappLink(phone, text)}
        target="_blank"
        rel="noopener noreferrer"
        // Closed a moment later: the link must open first.
        onClick={() => setTimeout(onSent, 300)}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-brand transition hover:bg-brand-700 active:translate-y-px"
      >
        <MessageCircle className="size-4" aria-hidden />
        {t("whatsapp.open")}
      </a>
    </>
  );
}

/** "WhatsApp" beside "Call", opening the dialog above. */
export function WhatsAppButton({
  memberId,
  purpose,
  className,
  iconClassName = "size-4",
}: {
  memberId: string;
  purpose: MessagePurpose;
  className: string;
  iconClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        <MessageCircle className={iconClassName} aria-hidden />
        {t("whatsapp.button")}
      </button>
      {open && (
        <WhatsAppDialog
          memberId={memberId}
          purpose={purpose}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

/** For an enquiry, who isn't a member yet: just the chat, no wording. */
export function WhatsAppLink({
  phone,
  className,
  iconClassName = "size-4",
}: {
  phone: string;
  className: string;
  iconClassName?: string;
}) {
  return (
    <a
      href={whatsappLink(phone)}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
    >
      <MessageCircle className={iconClassName} aria-hidden />
      {t("whatsapp.button")}
    </a>
  );
}
