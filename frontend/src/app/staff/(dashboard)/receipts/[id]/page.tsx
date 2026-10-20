"use client";

import { Download, MessageCircle, Share2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { TaxDocumentView } from "@/components/tax/TaxDocumentView";
import { methodLabel } from "@/components/money/PaymentFields";
import { Row } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import { errorMessage, paymentsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/dates";
import { download, receiptFile, share, type ReceiptLink } from "@/lib/receiptShare";
import { useLoad } from "@/lib/useLoad";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

/** The receipt to the member on WhatsApp, from GymBhai's number (§19.3). */
function SendOnWhatsApp({ id }: { id: string }) {
  const toast = useToast();
  const { can } = useAuth();
  const [sent, setSent] = useState(false);
  if (!can("messages.sms")) return null;
  return (
    <Button
      variant="secondary"
      disabled={sent}
      onClick={async () => {
        setSent(true);
        try {
          await paymentsApi.receiptWhatsApp(id);
          toast.success(t("receipt.whatsappSent"));
        } catch (err) {
          setSent(false);
          toast.error(errorMessage(err));
        }
      }}
    >
      <MessageCircle className="size-4" aria-hidden />
      {t("receipt.sendWhatsApp")}
    </Button>
  );
}

/**
 * Download and Share: the PDF is fetched as the page opens (§16.3, 8.4),
 * except a tax invoice's, whose every download is counted as a copy (§20.4):
 * fetched only when asked for, and shared as its link.
 */
function ShareButtons({ id, counted }: { id: string; counted: boolean }) {
  const toast = useToast();
  const [ready, setReady] = useState<{ link: ReceiptLink; file?: File } | null>(null);
  useEffect(() => {
    let gone = false;
    paymentsApi
      .receiptLink(id)
      .then(async (link) => ({
        link,
        file: counted ? undefined : await receiptFile(link),
      }))
      .then((found) => !gone && setReady(found))
      .catch(() => undefined);
    return () => {
      gone = true;
    };
  }, [id, counted]);
  return (
    <>
      <Button
        variant="secondary"
        disabled={!ready}
        onClick={async () => {
          if (!ready) return;
          download(ready.file ?? (await receiptFile(ready.link)));
        }}
      >
        <Download className="size-4" aria-hidden />
        {t("receipt.pdf")}
      </Button>
      <Button
        variant="secondary"
        disabled={!ready}
        onClick={async () => {
          if (!ready) return;
          const how = await share(ready.link, ready.file);
          if (how === "copied") toast.success(t("receipt.linkCopied"));
        }}
      >
        <Share2 className="size-4" aria-hidden />
        {t("receipt.share")}
      </Button>
    </>
  );
}

/**
 * A payment receipt — not a VAT invoice, and it says so (PLAN.md §10).
 * Sized to print on A5 or a phone screenshot.
 */
export default function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, setData, error } = useLoad(() => paymentsApi.receipt(id), [id]);
  const toast = useToast();
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!r) return <PageSkeleton label={t("common.loading")} />;
  const p = r.payment;
  const date = (iso: string | null) => formatDate(iso, r.date_display);
  // A VAT-registered gym's payment (§20.4): its tax invoice is what prints.
  const documents = r.tax_documents ?? [];

  async function print() {
    if (documents.length === 0) return window.print();
    try {
      // Counted first, so the paper says "Copy of original" from the second.
      setData(await paymentsApi.receiptPrinted(id));
      setTimeout(() => window.print(), 0);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const actions = (
    <div className="mb-4 flex flex-wrap justify-end gap-2 print:hidden">
      <Button variant="secondary" onClick={() => window.history.back()}>
        {t("common.back")}
      </Button>
      <ShareButtons id={id} counted={documents.length > 0} />
      {r.whatsapp && <SendOnWhatsApp id={id} />}
      <Button onClick={() => void print()}>{t("receipt.print")}</Button>
    </div>
  );

  if (documents.length > 0)
    return (
      <div className="mx-auto max-w-md space-y-4">
        {actions}
        {p.voided_at && (
          <p className="rounded bg-red-50 p-2 text-center text-sm font-semibold text-red-800 print:hidden">
            {t("receipt.voided", { reason: p.void_reason ?? "" })}
          </p>
        )}
        {documents.map((document) => (
          <TaxDocumentView
            key={document.id}
            document={document}
            receiptNo={p.receipt_no}
            method={methodLabel(p.method)}
            display={r.date_display}
          />
        ))}
      </div>
    );

  return (
    <div className="mx-auto max-w-md">
      {actions}
      <article className="rounded-2xl bg-surface p-6 shadow-card ring-1 ring-hairline print:p-0 print:ring-0">
        <header className="border-b border-dashed border-slate-300 pb-3 text-center">
          <h1 className="text-xl font-bold">{r.gym_name}</h1>
          {r.branch_name && <p className="text-sm text-slate-600">{r.branch_name}</p>}
          {r.gym_address && <p className="text-sm text-slate-600">{r.gym_address}</p>}
          {r.gym_phone && <p className="text-sm text-slate-600">{r.gym_phone}</p>}
          <p className="mt-2 text-sm font-semibold uppercase tracking-wide">
            {p.kind === "refund" ? t("receipt.refundTitle") : t("receipt.title")}
          </p>
        </header>
        {p.voided_at && (
          <p className="mt-3 rounded bg-red-50 p-2 text-center text-sm font-semibold text-red-800">
            {t("receipt.voided", { reason: p.void_reason ?? "" })}
          </p>
        )}
        <dl className="mt-3">
          <Row label={t("receipt.number")}>#{p.receipt_no}</Row>
          <Row label={t("receipt.date")}>
            {formatDateTime(p.paid_at, r.date_display)}
          </Row>
          <Row label={t("receipt.member")}>
            {r.member_name ? `${r.member_name} (${r.member_code})` : t("shop.walkIn")}
          </Row>
          {r.items && r.items.length > 0 && (
            <Row label={t("receipt.bought")}>
              <ul>
                {r.items.map((item) => (
                  <li key={item.name}>
                    {item.quantity} × {item.name} @ <Money paisa={item.unit_price} />
                  </li>
                ))}
              </ul>
            </Row>
          )}
          {r.discount ? (
            <Row label={t("shop.discount")}>
              <Money paisa={r.discount} />
            </Row>
          ) : null}
          {r.plan_name && <Row label={t("sale.plan")}>{r.plan_name}</Row>}
          {r.start_date && (
            <Row label={r.training ? t("receipt.training") : t("receipt.period")}>
              {date(r.start_date)} → {date(r.end_date)}
            </Row>
          )}
          <Row label={t("payment.method")}>{methodLabel(p.method)}</Row>
          {p.transaction_ref && (
            <Row label={t("payment.transactionRef")}>{p.transaction_ref}</Row>
          )}
        </dl>
        <div className="mt-3 flex items-center justify-between border-t border-dashed border-slate-300 pt-3">
          <span className="font-semibold">{t("receipt.amount")}</span>
          <Money paisa={p.amount} className="text-2xl font-bold" />
        </div>
        {r.dues_after !== null && r.dues_after > 0 && (
          <p className="mt-1 text-right text-sm text-amber-800">
            {t("receipt.duesAfter")} <Money paisa={r.dues_after} />
          </p>
        )}
        {p.received_by_name && (
          <p className="mt-3 text-sm text-slate-600">
            {t("receipt.receivedBy", { name: p.received_by_name })}
          </p>
        )}
        <p className="mt-4 text-center text-xs text-slate-500">
          {t("receipt.notInvoice")}
        </p>
      </article>
    </div>
  );
}
