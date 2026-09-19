"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Choice } from "@/components/Choice";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { Checkbox, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import {
  errorMessage,
  gymApi,
  type DateDisplay,
  type Gym,
  type PlanMonths,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { shrinkImage } from "@/lib/image";

export function GymSection({ gym }: { gym: Gym }) {
  const { refreshMe } = useAuth();
  const logoInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({
    name: gym.name,
    phone: gym.phone ?? "",
    address: gym.address ?? "",
    plan_months: gym.settings.plan_months,
    date_display: gym.settings.date_display,
    member_code_prefix: gym.settings.member_code_prefix,
    daily_summary_sms: gym.settings.daily_summary_sms,
  });
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    try {
      await gymApi.update({
        name: form.name,
        phone: form.phone || null,
        address: form.address || null,
        settings: {
          plan_months: form.plan_months,
          date_display: form.date_display,
          member_code_prefix: form.member_code_prefix.toUpperCase(),
          daily_summary_sms: form.daily_summary_sms,
        },
      });
      await refreshMe();
      setMessage({ tone: "success", text: t("common.saved") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  async function uploadLogo(file: File | undefined) {
    if (!file) return;
    try {
      await gymApi.uploadLogo(await shrinkImage(file, 512));
      await refreshMe();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={t("settings.gym")}>
      <form onSubmit={(e) => void save(e)} className="space-y-4">
        <div className="flex items-center gap-4">
          {gym.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={gym.logo_url}
              alt=""
              className="size-16 rounded-lg object-contain"
            />
          ) : (
            <span className="flex size-16 items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-500">
              {t("settings.noLogo")}
            </span>
          )}
          <Button variant="secondary" onClick={() => logoInput.current?.click()}>
            {t("settings.uploadLogo")}
          </Button>
          <input
            ref={logoInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void uploadLogo(e.target.files?.[0])}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("signup.gymName")}
            value={form.name}
            onChange={(name) => setForm({ ...form, name })}
            required
          />
          <Field
            label={t("settings.phone")}
            value={form.phone}
            onChange={(phone) => setForm({ ...form, phone })}
            type="tel"
          />
          <Field
            label={t("settings.address")}
            value={form.address}
            onChange={(address) => setForm({ ...form, address })}
          />
          <Field
            label={t("settings.memberCodePrefix")}
            value={form.member_code_prefix}
            onChange={(member_code_prefix) => setForm({ ...form, member_code_prefix })}
            help={t("settings.memberCodePrefixHelp", {
              example: `${form.member_code_prefix.toUpperCase()}-0042`,
            })}
          />
        </div>
        <Choice<PlanMonths>
          legend={t("signup.planMonths")}
          name="plan_months"
          value={form.plan_months}
          onChange={(plan_months) => setForm({ ...form, plan_months })}
          options={[
            {
              value: "bs",
              label: t("signup.planMonths.bs"),
              hint: t("signup.planMonths.bsExample"),
            },
            {
              value: "ad",
              label: t("signup.planMonths.ad"),
              hint: t("signup.planMonths.adExample"),
            },
          ]}
        />
        <p className="text-xs text-slate-500">{t("settings.planMonthsHelp")}</p>
        <Choice<DateDisplay>
          legend={t("signup.dateDisplay")}
          name="date_display"
          value={form.date_display}
          onChange={(date_display) => setForm({ ...form, date_display })}
          columns={3}
          options={[
            { value: "bs", label: t("signup.dateDisplay.bs") },
            { value: "ad", label: t("signup.dateDisplay.ad") },
            { value: "both", label: t("signup.dateDisplay.both") },
          ]}
        />
        <Checkbox
          label={t("settings.dailySummary")}
          checked={form.daily_summary_sms}
          onChange={(daily_summary_sms) => setForm({ ...form, daily_summary_sms })}
          hint={t("settings.dailySummaryHelp")}
        />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit">{t("common.save")}</Button>
      </form>
    </Card>
  );
}

export function CheckInRulesSection({ gym }: { gym: Gym }) {
  const { refreshMe } = useAuth();
  const [form, setForm] = useState({
    dues_rule: gym.settings.dues_rule,
    grace_days: String(gym.settings.grace_days),
    rescan_minutes: String(gym.settings.rescan_minutes),
  });
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    try {
      await gymApi.updateCheckInRules({
        dues_rule: form.dues_rule,
        grace_days: Number(form.grace_days),
        rescan_minutes: Number(form.rescan_minutes),
      });
      await refreshMe();
      setMessage({ tone: "success", text: t("common.saved") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={t("settings.checkInRules")}>
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <Select
          label={t("settings.duesRule")}
          value={form.dues_rule}
          onChange={(dues_rule) => setForm({ ...form, dues_rule })}
          options={[
            { value: "allow", label: t("settings.duesRule.allow") },
            { value: "warn", label: t("settings.duesRule.warn") },
            { value: "refuse", label: t("settings.duesRule.refuse") },
          ]}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("settings.graceDays")}
            value={form.grace_days}
            onChange={(grace_days) => setForm({ ...form, grace_days })}
            type="number"
            inputMode="numeric"
            help={t("settings.graceDaysHelp")}
          />
          <Field
            label={t("settings.rescanMinutes")}
            value={form.rescan_minutes}
            onChange={(rescan_minutes) => setForm({ ...form, rescan_minutes })}
            type="number"
            inputMode="numeric"
            help={t("settings.rescanMinutesHelp")}
          />
        </div>
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit">{t("common.save")}</Button>
      </form>
    </Card>
  );
}
