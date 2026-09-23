"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice as Alert } from "@/components/Notice";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Checkbox, Select, TextArea } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { branchesApi, errorMessage, messagesApi, type NoticeInput } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** Notices for the member app, optionally by SMS — with the cost shown first. */
export default function NoticesPage() {
  const { can } = useAuth();
  const { display } = useGymCalendar();
  const notices = useLoad(() => messagesApi.notices(), []);
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  const [draft, setDraft] = useState<NoticeInput>({
    title: "",
    body: "",
    send_sms: false,
  });
  const [branchId, setBranchId] = useState("all");
  const [cost, setCost] = useState<{
    recipients: number;
    total_credits: number;
    balance: number;
  } | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  const input = (): NoticeInput => ({
    ...draft,
    branch_id: branchId === "all" ? null : branchId,
  });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      // With SMS, show what it costs and ask before spending credits.
      if (draft.send_sms && !cost) {
        setCost(await messagesApi.noticeCost(input()));
        return;
      }
      const notice = await messagesApi.publishNotice(input());
      setDraft({ title: "", body: "", send_sms: false });
      setCost(null);
      setMessage({
        tone: "success",
        text: notice.send_sms
          ? t("notices.publishedSms", { count: notice.sms_count })
          : t("notices.published"),
      });
      notices.reload();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("notices.title")} />
      <Card title={t("notices.new")}>
        <form onSubmit={(e) => void submit(e)} className="space-y-3">
          <Field
            label={t("notices.titleField")}
            value={draft.title}
            onChange={(title) => {
              setDraft({ ...draft, title });
              setCost(null);
            }}
            required
          />
          <TextArea
            label={t("notices.body")}
            value={draft.body}
            rows={4}
            onChange={(body) => {
              setDraft({ ...draft, body });
              setCost(null);
            }}
            required
          />
          {branches.length > 1 && (
            <Select
              label={t("sale.branch")}
              value={branchId}
              onChange={(value) => {
                setBranchId(value);
                setCost(null);
              }}
              options={[
                { value: "all", label: t("extendAll.allBranches") },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          )}
          {can("messages.sms") && (
            <Checkbox
              label={t("notices.sendSms")}
              checked={draft.send_sms}
              onChange={(send_sms) => {
                setDraft({ ...draft, send_sms });
                setCost(null);
              }}
              hint={t("notices.sendSmsHelp")}
            />
          )}
          {cost && (
            <Alert tone={cost.total_credits > cost.balance ? "warning" : "info"}>
              {t("notices.cost", {
                recipients: cost.recipients,
                credits: cost.total_credits,
                balance: cost.balance,
              })}
              {cost.total_credits > cost.balance && ` ${t("notices.notEnough")}`}
            </Alert>
          )}
          {message && <Alert tone={message.tone}>{message.text}</Alert>}
          <Button type="submit">
            {draft.send_sms && !cost
              ? t("notices.checkCost")
              : cost
                ? t("notices.confirmSend")
                : t("notices.publish")}
          </Button>
        </form>
      </Card>
      <Card title={t("notices.recent")}>
        {notices.data?.length === 0 && <EmptyState title={t("notices.none")} />}
        <ul className="divide-y divide-hairline">
          {notices.data?.map((n) => (
            <li key={n.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium">{n.title}</p>
                <p className="text-sm whitespace-pre-line text-slate-700">{n.body}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {formatDateTime(n.published_at, display)}
                  {n.send_sms && ` · ${t("notices.smsTo", { count: n.sms_count })}`}
                </p>
              </div>
              <Button
                variant="ghost"
                onClick={async () => {
                  if (!window.confirm(t("notices.deleteConfirm"))) return;
                  await messagesApi.deleteNotice(n.id);
                  notices.reload();
                }}
              >
                {t("notices.delete")}
              </Button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
