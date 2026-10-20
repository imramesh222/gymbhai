"use client";

import { Check, CheckCheck, MessageCircle, MessageSquare } from "lucide-react";
import Link from "next/link";

import { t, type MessageKey } from "@/i18n";
import type { SmsMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import type { DateDisplay } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  sent: "text-emerald-700",
  queued: "text-slate-500",
  failed: "text-red-700",
  no_credit: "text-amber-700",
};

/**
 * Where a message stands. A WhatsApp message also has Meta's word on it
 * (PLAN.md §19.3): delivered to the phone, then read.
 */
export function messageStatus(m: SmsMessage): string {
  if (m.channel === "whatsapp" && m.status === "sent") {
    if (m.read_at) return t("sms.status.read");
    if (m.delivered_at) return t("sms.status.delivered");
  }
  return t(`sms.status.${m.status}` as MessageKey);
}

/** One message in the log or on a member's Messages tab: SMS or WhatsApp. */
export function MessageItem({
  message: m,
  display,
  showTo = false,
}: {
  message: SmsMessage;
  display: DateDisplay;
  showTo?: boolean;
}) {
  const whatsapp = m.channel === "whatsapp";
  const Icon = whatsapp ? MessageCircle : MessageSquare;
  const Tick = m.read_at ? CheckCheck : m.delivered_at ? CheckCheck : Check;
  return (
    <li className="py-2.5 text-sm">
      <div className="flex justify-between gap-3">
        <span className="flex min-w-0 items-center gap-1.5 font-medium">
          <Icon
            className={`size-4 shrink-0 ${whatsapp ? "text-emerald-600" : "text-slate-400"}`}
            aria-label={t(whatsapp ? "sms.channel.whatsapp" : "sms.channel.sms")}
          />
          {showTo &&
            (m.member_id ? (
              <Link href={`/staff/members/${m.member_id}`} className="hover:underline">
                {m.to}
              </Link>
            ) : (
              m.to
            ))}
          <span className="truncate font-normal text-slate-500">
            {showTo && "· "}
            {t(`sms.kind.${m.kind}` as MessageKey)}
          </span>
        </span>
        <span
          className={`flex shrink-0 items-center gap-1 ${
            m.read_at ? "text-sky-700" : (STATUS_STYLE[m.status] ?? "")
          }`}
        >
          {whatsapp && m.status === "sent" && <Tick className="size-3.5" aria-hidden />}
          {messageStatus(m)}
        </span>
      </div>
      <p className="mt-0.5 whitespace-pre-line text-slate-700">{m.body}</p>
      <p className="text-xs text-slate-500">
        {formatDateTime(m.created_at, display)} ·{" "}
        {whatsapp
          ? t("sms.whatsappCredits", { count: m.segments })
          : t("sms.parts", { count: m.segments, characters: m.body.length })}
        {m.error && ` · ${m.error}`}
      </p>
    </li>
  );
}
