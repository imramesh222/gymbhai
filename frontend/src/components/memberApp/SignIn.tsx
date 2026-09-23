"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { t } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { memberApi, type PublicGym } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

/** Phone or email -> 6-digit code -> (shared phone) who are you? (§7) */
export function SignIn() {
  const { slug, signedIn } = useMember();
  const gym = useLoad(() => memberApi.gym(slug), [slug]);
  const [who, setWho] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [choose, setChoose] = useState<{ id: string; name: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const target = () =>
    who.includes("@") ? { email: who.trim() } : { phone: who.trim() };

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (gym.error) {
    return (
      <div className="p-6">
        <Notice tone="error">{t("app.noSuchGym")}</Notice>
      </div>
    );
  }

  return (
    <main className="relative isolate mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(75%_45%_at_50%_28%,var(--color-brand-200),transparent)] opacity-80"
      />
      <GymHeader gym={gym.data} />
      {!sentTo ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const result = await memberApi.requestCode(slug, target());
              setSentTo(result.sent_to);
            });
          }}
          className="mt-7 space-y-4 rounded-2xl bg-surface p-5 shadow-raised ring-1 ring-hairline"
        >
          <Field
            label={t("app.signIn.who")}
            value={who}
            onChange={setWho}
            inputMode="tel"
            autoComplete="tel"
            required
            help={t("app.signIn.whoHelp")}
          />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" size="lg" block disabled={pending}>
            {t("app.signIn.sendCode")}
          </Button>
        </form>
      ) : choose ? (
        <div className="mt-7 space-y-3 rounded-2xl bg-surface p-5 shadow-raised ring-1 ring-hairline">
          <p className="font-medium">{t("app.signIn.whoAreYou")}</p>
          {choose.map((person) => (
            <Button
              key={person.id}
              variant="secondary"
              block
              onClick={() =>
                run(async () => {
                  signedIn(
                    await memberApi.verifyCode(slug, {
                      ...target(),
                      code,
                      member_id: person.id,
                    }),
                  );
                })
              }
            >
              {person.name}
            </Button>
          ))}
          {error && <Notice tone="error">{error}</Notice>}
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const result = await memberApi.verifyCode(slug, { ...target(), code });
              if (result.choose) setChoose(result.choose);
              else signedIn(result);
            });
          }}
          className="mt-7 space-y-4 rounded-2xl bg-surface p-5 shadow-raised ring-1 ring-hairline"
        >
          <p className="text-sm text-slate-600">
            {t("app.signIn.sent", { to: sentTo })}
          </p>
          <Field
            label={t("app.signIn.code")}
            value={code}
            onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
          />
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" size="lg" block disabled={pending || code.length !== 6}>
            {t("app.signIn.submit")}
          </Button>
          <button
            type="button"
            onClick={() => {
              setSentTo(null);
              setCode("");
            }}
            className="w-full text-sm font-medium text-slate-500 transition hover:text-slate-800"
          >
            {t("app.signIn.again")}
          </button>
        </form>
      )}
    </main>
  );
}

function GymHeader({ gym }: { gym: PublicGym | null }) {
  if (!gym)
    return <p className="text-center text-sm text-slate-500">{t("common.loading")}</p>;
  return (
    <div className="text-center">
      {gym.logo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={gym.logo_url}
          alt=""
          className="mx-auto mb-4 size-20 rounded-2xl bg-white object-contain p-2 shadow-card ring-1 ring-hairline"
        />
      )}
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">{gym.name}</h1>
      <p className="mt-1 text-slate-600">{t("app.signIn.title")}</p>
    </div>
  );
}
