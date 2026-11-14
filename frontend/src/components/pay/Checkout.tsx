"use client";

import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { QrCode } from "@/components/QrCode";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { errorMessage } from "@/lib/api";
import { memberApi } from "@/lib/memberApi";
import type { PayPage } from "@shared/types";

/** The wallet's name, as the gym's accounts show it. */
export function walletName(page: Pick<PayPage, "provider">): string {
  return t(`account.${page.provider}` as MessageKey);
}

/** Where "back" goes: the phone app, or the gym's web app. */
function backLink(page: PayPage): { href: string; label: string } {
  // The app's own link: a gym's own app, or Expo Go, isn't gymbhai://.
  return page.from_app
    ? { href: page.return_to ?? "gymbhai://renew", label: t("pay.backToApp") }
    : { href: `/${page.gym_slug}`, label: t("pay.backToGym", { gym: page.gym_name }) };
}

function Frame({ page, children }: { page: PayPage; children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-md space-y-5 px-4 py-10 text-center">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">
          {t("pay.title", { gym: page.gym_name })}
        </h1>
        <p className="text-slate-600">
          {t("pay.for", { plan: page.plan_name })} ·{" "}
          <Money paisa={page.amount} className="font-semibold" />
        </p>
        {page.test && (
          <p className="inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-200">
            {t("pay.test")}
          </p>
        )}
      </div>
      {children}
    </main>
  );
}

/** How it ended, or that the wallet hasn't said yet. */
export function Outcome({
  page,
  onCheck,
  checking,
}: {
  page: PayPage;
  onCheck: () => void;
  checking: boolean;
}) {
  const wallet = walletName(page);
  const back = backLink(page);
  let message: string;
  let tone: "success" | "warning" | "error" | "info" = "info";
  if (page.status === "paid") {
    tone = "success";
    message = page.test
      ? t("pay.paidTest", { wallet })
      : page.approved
        ? t("pay.paid")
        : t("pay.paidForDesk");
  } else if (page.status === "started") {
    message = t("pay.notYet", { wallet });
  } else {
    tone = "warning";
    message = t("pay.notPaid");
  }
  return (
    <Frame page={page}>
      <p className="text-4xl" aria-hidden>
        {page.status === "paid" ? "✓" : page.status === "started" ? "⏳" : "✕"}
      </p>
      <Notice tone={tone}>{message}</Notice>
      <div className="flex flex-col gap-2">
        {page.status === "started" && (
          <Button variant="secondary" onClick={onCheck} disabled={checking}>
            {checking ? t("pay.checking", { wallet }) : t("pay.checkAgain")}
          </Button>
        )}
        <a
          href={back.href}
          className="rounded-xl bg-brand-600 px-4 py-2.5 font-semibold text-white"
        >
          {back.label}
        </a>
      </div>
    </Frame>
  );
}

/**
 * The payment while it's open (PLAN.md §20.2): eSewa's signed form, sent on
 * by itself; Khalti's page; Fonepay's QR, asked about every few seconds; or,
 * in development, the pretend wallet. Whatever the wallet sends back is not
 * believed: the server asks the wallet.
 */
export function OpenCheckout({
  token,
  page,
  onChange,
}: {
  token: string;
  page: PayPage;
  onChange: (page: PayPage) => void;
}) {
  const wallet = walletName(page);
  const checkout = page.checkout!;
  const form = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (checkout.kind === "form") form.current?.submit();
    if (checkout.kind === "redirect" && checkout.url)
      window.location.replace(checkout.url);
  }, [checkout]);

  // The QR is paid in another app: ask the wallet while it's on the screen.
  useEffect(() => {
    if (checkout.kind !== "qr") return;
    const timer = window.setInterval(() => {
      memberApi
        .payCheck(token)
        .then((next) => next.status !== "started" && onChange(next))
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [checkout.kind, token, onChange]);

  async function pretend(paid: boolean) {
    setPending(true);
    setError(null);
    try {
      onChange(await memberApi.payPretend(token, paid));
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  async function saveQr() {
    const url = await QRCode.toDataURL(checkout.qr!, { margin: 2, width: 720 });
    const link = document.createElement("a");
    link.href = url;
    link.download = `${page.gym_slug}-fonepay.png`;
    link.click();
  }

  return (
    <Frame page={page}>
      {checkout.kind === "form" && (
        <form
          ref={form}
          method="POST"
          action={checkout.url ?? ""}
          className="space-y-3"
        >
          {Object.entries(checkout.fields).map(([name, value]) => (
            <input key={name} type="hidden" name={name} value={value} />
          ))}
          <p className="text-slate-600">{t("pay.going", { wallet })}</p>
          <Button type="submit">{t("pay.goNow", { wallet })}</Button>
        </form>
      )}
      {checkout.kind === "redirect" && (
        <div className="space-y-3">
          <p className="text-slate-600">{t("pay.going", { wallet })}</p>
          <a
            href={checkout.url ?? "#"}
            className="inline-block rounded-xl bg-brand-600 px-4 py-2.5 font-semibold text-white"
          >
            {t("pay.goNow", { wallet })}
          </a>
        </div>
      )}
      {checkout.kind === "qr" && checkout.qr && (
        <div className="space-y-3">
          <div className="mx-auto w-fit rounded-xl bg-white p-3 ring-1 ring-hairline">
            <QrCode value={checkout.qr} size={240} label={t("pay.goNow", { wallet })} />
          </div>
          <p className="text-sm text-slate-600">{t("pay.qrHelp")}</p>
          <Button variant="secondary" onClick={() => saveQr()}>
            {t("pay.saveQr")}
          </Button>
          <p className="text-sm text-slate-500" aria-live="polite">
            {t("pay.waiting")}
          </p>
        </div>
      )}
      {checkout.kind === "console" && (
        <div className="space-y-3 rounded-xl bg-white p-4 ring-1 ring-hairline">
          <p className="text-sm text-slate-600">{t("pay.pretend", { wallet })}</p>
          <div className="flex justify-center gap-2">
            <Button onClick={() => pretend(true)} disabled={pending}>
              {t("pay.pretendPay")}
            </Button>
            <Button
              variant="secondary"
              onClick={() => pretend(false)}
              disabled={pending}
            >
              {t("pay.pretendCancel")}
            </Button>
          </div>
        </div>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </Frame>
  );
}

export function Expired() {
  return (
    <main className="mx-auto max-w-md px-4 py-10">
      <Notice tone="error">{t("pay.expired")}</Notice>
    </main>
  );
}

export function Loading() {
  return <p className="p-10 text-center text-slate-500">{t("common.loading")}</p>;
}
