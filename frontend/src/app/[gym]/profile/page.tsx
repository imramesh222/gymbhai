"use client";

import { Camera } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { PushSetting } from "@/components/memberApp/PushPrompt";
import { Notice } from "@/components/Notice";
import { Row } from "@/components/ui/Card";
import { Checkbox, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { shrinkImage } from "@/lib/image";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";
import { describeDevice } from "@/lib/userAgent";

/** A new email: a code to it first, then it's theirs (PLAN.md §16.3, 8.5). */
function EmailChange({ onDone }: { onDone: () => void }) {
  const { refresh } = useMember();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          if (!sent) {
            await memberApi.changeEmail(email);
            setSent(true);
          } else {
            await memberApi.confirmEmail(email, code);
            await refresh();
            onDone();
          }
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <Field
        label={t("app.profile.newEmail")}
        type="email"
        value={email}
        onChange={(value) => {
          setEmail(value);
          setSent(false);
        }}
        required
      />
      {sent && (
        <>
          <p className="text-sm text-slate-600">
            {t("app.profile.codeSent", { email })}
          </p>
          <Field
            label={t("app.signIn.code")}
            value={code}
            onChange={setCode}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
          />
        </>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button type="submit">
          {sent ? t("app.profile.confirm") : t("app.profile.sendCode")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function EmergencyContact({ initial }: { initial: string | null }) {
  const { refresh } = useMember();
  const [value, setValue] = useState(initial ?? "");
  const [state, setState] = useState<"idle" | "saved" | string>("idle");
  const dirty = value.trim() !== (initial ?? "");
  return (
    <form
      className="space-y-2"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await memberApi.updateMe({ emergency_contact: value.trim() || null });
          await refresh();
          setState("saved");
        } catch (err) {
          setState(errorMessage(err));
        }
      }}
    >
      <Field
        label={t("app.profile.emergency")}
        value={value}
        onChange={(next) => {
          setValue(next);
          setState("idle");
        }}
        help={t("app.profile.emergencyHelp")}
        optional
      />
      {state === "saved" && !dirty && (
        <p className="text-sm text-emerald-700">{t("app.profile.saved")}</p>
      )}
      {state !== "idle" && state !== "saved" && <Notice tone="error">{state}</Notice>}
      {dirty && (
        <Button type="submit" variant="secondary">
          {t("common.save")}
        </Button>
      )}
    </form>
  );
}

/** Their own language, or the gym's (PLAN.md §16.6). */
function MemberLanguage() {
  const { me, refresh } = useMember();
  if (!me) return null;
  const gymLanguage = me.language === "ne" && !me.own_language ? "नेपाली" : "English";
  return (
    <div className="rounded-2xl bg-white p-4">
      <Select<"gym" | "en" | "ne">
        label={t("language.title")}
        value={me.own_language ?? "gym"}
        onChange={async (choice) => {
          await memberApi.updateMe({ language: choice === "gym" ? null : choice });
          await refresh();
        }}
        options={[
          {
            value: "gym",
            label: t("language.gymDefault", {
              language: me.own_language ? t("language.gyms") : gymLanguage,
            }),
          },
          { value: "en", label: "English" },
          { value: "ne", label: "नेपाली" },
        ]}
      />
    </div>
  );
}

/** Messages from the gym on WhatsApp, their own say (PLAN.md §19.3). */
function WhatsAppSetting() {
  const { me, refresh } = useMember();
  const [error, setError] = useState<string | null>(null);
  if (!me?.whatsapp) return null;
  return (
    <div className="rounded-2xl bg-white p-4">
      <Checkbox
        label={t("app.profile.whatsapp")}
        hint={t("app.profile.whatsappHelp")}
        checked={me.whatsapp_agreed ?? false}
        onChange={async (on) => {
          setError(null);
          try {
            await memberApi.updateMe({ whatsapp_agreed: on });
            await refresh();
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
      />
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}

/** Where they're signed in, and signing a lost phone out (PLAN.md §17.5). */
function MyDevices() {
  const { me } = useMember();
  const { data, reload } = useLoad(() => memberApi.devices(), []);
  const [message, setMessage] = useState<string | null>(null);
  if (!me || !data) return null;
  const others = data.some((device) => !device.current);
  const display = me.gym.date_display;
  async function run(action: () => Promise<string>) {
    try {
      setMessage(await action());
      reload();
    } catch (err) {
      setMessage(errorMessage(err));
    }
  }
  return (
    <div className="space-y-2 rounded-2xl bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{t("sessions.title")}</h2>
        {others && (
          <button
            type="button"
            className="text-sm font-semibold text-brand-700"
            onClick={() =>
              void run(async () => {
                const { signed_out } = await memberApi.signOutOtherDevices();
                return t("sessions.signedOutOthers", { count: signed_out });
              })
            }
          >
            {t("sessions.signOutOthers")}
          </button>
        )}
      </div>
      <ul className="divide-y divide-hairline">
        {data.map((device) => (
          <li key={device.id} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0 text-sm">
              <p className="font-medium">
                {deviceName(device.device_label)}
                {device.current && (
                  <span className="ml-2 text-xs font-semibold text-emerald-700">
                    {t("sessions.thisDevice")}
                  </span>
                )}
              </p>
              {device.last_used_at && (
                <p className="text-xs text-slate-500">
                  {t("sessions.lastUsed", {
                    when: formatDateTime(device.last_used_at, display),
                  })}
                </p>
              )}
            </div>
            {!device.current && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  void run(async () => {
                    await memberApi.signOutDevice(device.id);
                    return t("sessions.signedOut");
                  })
                }
              >
                {t("sessions.signOut")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {message && <p className="text-sm text-slate-600">{message}</p>}
    </div>
  );
}

function deviceName(userAgent: string | null): string {
  const { browser, system } = describeDevice(userAgent);
  if (browser && system) return t("sessions.browserOn", { browser, system });
  return browser ?? system ?? t("sessions.unknown");
}

export default function MemberProfile() {
  const { me, slug, signOut, refresh } = useMember();
  const photo = useRef<HTMLInputElement>(null);
  const [editingEmail, setEditingEmail] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  if (!me) return null;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => photo.current?.click()}
          className="relative shrink-0 rounded-full"
          aria-label={t("app.profile.photo")}
        >
          {me.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={me.photo_url}
              alt=""
              className="size-16 rounded-full object-cover"
            />
          ) : (
            <span className="flex size-16 items-center justify-center rounded-full bg-slate-100 text-slate-500">
              <Camera className="size-6" aria-hidden />
            </span>
          )}
          <span className="absolute -right-1 -bottom-1 rounded-full bg-white p-1 shadow ring-1 ring-hairline">
            <Camera className="size-3.5 text-slate-700" aria-hidden />
          </span>
        </button>
        <input
          ref={photo}
          type="file"
          accept="image/*"
          capture="user"
          className="hidden"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setPhotoError(null);
            try {
              await memberApi.uploadPhoto(await shrinkImage(file));
              await refresh();
            } catch (err) {
              setPhotoError(errorMessage(err));
            }
          }}
        />
        <div>
          <h1 className="text-xl font-semibold">{me.name}</h1>
          <p className="text-sm text-slate-500">{me.member_code}</p>
        </div>
      </div>
      {photoError && <Notice tone="error">{photoError}</Notice>}
      <p className="text-xs text-slate-500">{t("app.profile.photoHelp")}</p>

      <div className="space-y-3 rounded-2xl bg-white p-4">
        <dl>
          <Row label={t("member.phone")}>{me.phone}</Row>
          <Row label={t("member.email")}>
            <span className="inline-flex items-center gap-2">
              {me.email ?? "—"}
              {!editingEmail && (
                <button
                  type="button"
                  className="text-sm font-semibold text-brand-700"
                  onClick={() => setEditingEmail(true)}
                >
                  {t("app.profile.edit")}
                </button>
              )}
            </span>
          </Row>
        </dl>
        {editingEmail && <EmailChange onDone={() => setEditingEmail(false)} />}
        <EmergencyContact initial={me.emergency_contact} />
      </div>
      <p className="text-xs text-slate-500">{t("app.profile.readOnly")}</p>
      <MemberLanguage />
      <PushSetting slug={slug} />
      <WhatsAppSetting />
      <MyDevices />
      <Link
        href={`/${slug}/notices`}
        className="block text-sm text-brand-700 underline"
      >
        {t("app.notices")}
      </Link>
      <Button variant="secondary" block onClick={() => void signOut()}>
        {t("common.signOut")}
      </Button>
    </div>
  );
}
