"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { t } from "@/i18n";
import { errorMessage, gymApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { me } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await gymApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setMessage({ tone: "success", text: t("profile.passwordChanged") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="max-w-md space-y-4">
      <PageHeader
        title={me?.staff.name ?? ""}
        subtitle={me?.staff.email ?? me?.staff.phone ?? ""}
      />
      <Card title={t("profile.changePassword")}>
        <form onSubmit={(e) => void submit(e)} className="space-y-3">
          <Field
            label={t("profile.currentPassword")}
            value={current}
            onChange={setCurrent}
            type="password"
            autoComplete="current-password"
            required
          />
          <Field
            label={t("profile.newPassword")}
            value={next}
            onChange={setNext}
            type="password"
            autoComplete="new-password"
            help={t("signup.passwordHelp")}
            required
          />
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          <Button type="submit">{t("profile.changePassword")}</Button>
        </form>
      </Card>
    </div>
  );
}
