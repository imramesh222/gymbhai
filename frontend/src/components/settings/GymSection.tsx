"use client";

import Link from "next/link";
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
import { useUnsavedWarning } from "@/lib/unsaved";
import { shrinkImage } from "@/lib/image";

function savedForm(gym: Gym) {
  return {
    name: gym.name,
    phone: gym.phone ?? "",
    address: gym.address ?? "",
    plan_months: gym.settings.plan_months,
    date_display: gym.settings.date_display,
    member_code_prefix: gym.settings.member_code_prefix,
    daily_summary_sms: gym.settings.daily_summary_sms,
    show_busyness: gym.settings.show_busyness,
    join_form: gym.settings.join_form,
    language: gym.settings.language,
    digits: gym.settings.digits,
  };
}

export function GymSection({ gym }: { gym: Gym }) {
  const { refreshMe } = useAuth();
  const logoInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState(() => savedForm(gym));
  // The gym as saved comes back through refreshMe; anything else is unsaved.
  const dirty = JSON.stringify(form) !== JSON.stringify(savedForm(gym));
  useUnsavedWarning(dirty);
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
          show_busyness: form.show_busyness,
          join_form: form.join_form,
          language: form.language,
          digits: form.digits,
        },
      });
      await refreshMe();
      setForm((f) => ({
        ...f,
        member_code_prefix: f.member_code_prefix.toUpperCase(),
      }));
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
        <div className="grid gap-3 sm:grid-cols-2">
          <Select<"en" | "ne">
            label={t("settings.language")}
            value={form.language}
            onChange={(language) => setForm({ ...form, language })}
            options={[
              { value: "en", label: "English" },
              { value: "ne", label: "नेपाली" },
            ]}
          />
          <Select<"western" | "nepali">
            label={t("settings.digits")}
            value={form.digits}
            onChange={(digits) => setForm({ ...form, digits })}
            options={[
              { value: "western", label: t("settings.digits.western") },
              { value: "nepali", label: t("settings.digits.nepali") },
            ]}
          />
        </div>
        <p className="text-sm text-slate-500">{t("settings.languageHelp")}</p>
        <Checkbox
          label={t("settings.dailySummary")}
          checked={form.daily_summary_sms}
          onChange={(daily_summary_sms) => setForm({ ...form, daily_summary_sms })}
          hint={t("settings.dailySummaryHelp")}
        />
        <Checkbox
          label={t("settings.showBusyness")}
          checked={form.show_busyness}
          onChange={(show_busyness) => setForm({ ...form, show_busyness })}
          hint={t("settings.showBusynessHelp")}
        />
        <Checkbox
          label={t("settings.joinForm")}
          checked={form.join_form}
          onChange={(join_form) => setForm({ ...form, join_form })}
          hint={t("settings.joinFormHelp")}
        />
        {dirty && <Notice tone="warning">{t("settings.unsaved")}</Notice>}
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
    not_visiting_days: String(gym.settings.not_visiting_days),
    kiosk_offline_days: String(gym.settings.kiosk_offline_days ?? 3),
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
        not_visiting_days: Number(form.not_visiting_days),
        kiosk_offline_days: Number(form.kiosk_offline_days),
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
          <Field
            label={t("settings.notVisitingDays")}
            value={form.not_visiting_days}
            onChange={(not_visiting_days) => setForm({ ...form, not_visiting_days })}
            type="number"
            inputMode="numeric"
            help={t("settings.notVisitingDaysHelp")}
          />
          <Field
            label={t("settings.kioskOfflineDays")}
            value={form.kiosk_offline_days}
            onChange={(kiosk_offline_days) => setForm({ ...form, kiosk_offline_days })}
            type="number"
            inputMode="numeric"
            help={t("settings.kioskOfflineDaysHelp")}
          />
        </div>
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit">{t("common.save")}</Button>
      </form>
    </Card>
  );
}

/**
 * Settings → Security: the owner alone (PLAN.md §16.1). Requiring two-step
 * sign-in needs the owner's own turned on first.
 */
export function SecuritySection({ gym }: { gym: Gym }) {
  const { me, refreshMe } = useAuth();
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const ownOn = me?.staff.two_step_enabled ?? false;

  async function change(required: boolean) {
    try {
      await gymApi.updateSecurity(required);
      await refreshMe();
      setMessage({ tone: "success", text: t("common.saved") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={t("settings.security")}>
      <div className="space-y-3">
        <Checkbox
          label={t("settings.requireTwoStep")}
          hint={t("settings.requireTwoStepHint")}
          checked={gym.settings.require_two_step}
          disabled={!ownOn && !gym.settings.require_two_step}
          onChange={(checked) => void change(checked)}
        />
        {!ownOn && (
          <Notice>
            {t("settings.requireTwoStepFirst")}{" "}
            <Link
              href="/staff/profile"
              className="font-semibold text-brand-700 hover:underline"
            >
              {t("nav.profile")}
            </Link>
          </Notice>
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    </Card>
  );
}
