import { Money } from "@/components/ui/Money";
import { t } from "@/i18n";
import type { TaxDocument } from "@/lib/api";
import { formatDateTime, type DateDisplay } from "@/lib/dates";

/**
 * A tax invoice or credit note as it prints (PLAN.md §20.4): the seller and
 * their PAN, the number in its fiscal year, the dates in BS and AD, the
 * buyer, the lines before VAT, the taxable amount, VAT and the total.
 */
export function TaxDocumentView({
  document: d,
  receiptNo,
  method,
  display,
}: {
  document: TaxDocument;
  receiptNo: number;
  method: string;
  display: DateDisplay;
}) {
  const credit = d.kind === "credit_note";
  return (
    <article className="rounded-2xl bg-surface p-6 shadow-card ring-1 ring-hairline print:break-after-page print:p-0 print:ring-0">
      <header className="border-b border-dashed border-slate-300 pb-3 text-center">
        <h1 className="text-xl font-bold">{d.seller.name}</h1>
        {d.seller.address && (
          <p className="text-sm text-slate-600">{d.seller.address}</p>
        )}
        <p className="text-sm text-slate-600">
          {t("tax.sellerPan", { pan: d.seller.pan ?? "" })}
        </p>
        <p className="mt-2 text-sm font-semibold uppercase tracking-wide">
          {credit ? t("tax.creditNote") : t("tax.invoice")}
        </p>
        {d.prints > 1 && (
          <p className="text-xs text-slate-500">{t("tax.copy", { n: d.prints })}</p>
        )}
      </header>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-500">
          {credit ? t("tax.creditNo") : t("tax.invoiceNo")}
        </dt>
        <dd className="text-right font-semibold">{d.number}</dd>
        <dt className="text-slate-500">{t("tax.fiscalYear")}</dt>
        <dd className="text-right">{d.fiscal_year}</dd>
        <dt className="text-slate-500">{t("tax.date")}</dt>
        <dd className="text-right">
          {d.issued_on_bs} BS ·{" "}
          {formatDateTime(d.issued_at, display === "bs" ? "ad" : display)}
        </dd>
        <dt className="text-slate-500">{t("receipt.number")}</dt>
        <dd className="text-right">#{receiptNo}</dd>
        {credit && d.ref_number !== null && (
          <>
            <dt className="text-slate-500">{t("tax.reason")}</dt>
            <dd className="text-right">
              {t("tax.against", {
                number: d.ref_number,
                year: d.ref_fiscal_year ?? "",
              })}
              {d.reason && ` · ${d.reason}`}
            </dd>
          </>
        )}
        <dt className="text-slate-500">{t("tax.buyer")}</dt>
        <dd className="text-right">
          {d.buyer_name}
          {d.buyer_address && (
            <span className="block text-slate-600">{d.buyer_address}</span>
          )}
        </dd>
        {d.buyer_pan && (
          <>
            <dt className="text-slate-500">{t("tax.buyerPan")}</dt>
            <dd className="text-right">{d.buyer_pan}</dd>
          </>
        )}
        <dt className="text-slate-500">{t("payment.method")}</dt>
        <dd className="text-right">{method}</dd>
      </dl>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs text-slate-500">
            <th className="py-1 text-left font-medium">{t("tax.description")}</th>
            <th className="py-1 text-right font-medium">{t("tax.qty")}</th>
            <th className="py-1 text-right font-medium">{t("tax.rate")}</th>
            <th className="py-1 text-right font-medium">{t("tax.amount")}</th>
          </tr>
        </thead>
        <tbody>
          {d.lines.map((line, i) => (
            <tr key={i} className="align-top">
              <td className="py-1 pr-2">{line.description}</td>
              <td className="py-1 text-right tabular-nums">{line.quantity}</td>
              <td className="py-1 text-right">
                <Money paisa={line.rate} />
              </td>
              <td className="py-1 text-right">
                <Money paisa={line.amount} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="mt-3 space-y-1 border-t border-dashed border-slate-300 pt-3 text-sm">
        <div className="flex justify-between">
          <dt>{t("tax.taxable")}</dt>
          <dd>
            <Money paisa={d.taxable} />
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>{t("tax.vat")}</dt>
          <dd>
            <Money paisa={d.vat} />
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="font-semibold">{t("tax.total")}</dt>
          <dd>
            <Money paisa={d.total} className="text-2xl font-bold" />
          </dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-slate-600">
        {t("tax.inWords", { words: d.total_in_words })}
      </p>
    </article>
  );
}
