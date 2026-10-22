"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { QrCode } from "@/components/QrCode";
import { Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { branchesApi, gymApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/useLoad";

// An A4 sheet's width in CSS pixels.
const A4_WIDTH = (210 * 96) / 25.4;

/** The gym QR poster (§4.1): A4, logo, "Scan to see your membership". */
export default function PosterPage() {
  const { me, can, refreshMe } = useAuth();
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  // Opening the poster ticks it off Today's setup checklist.
  const printed = me?.gym?.settings.poster_printed ?? true;
  const mayMark = can("setup.gym");
  useEffect(() => {
    if (printed || !mayMark) return;
    gymApi
      .update({ settings: { poster_printed: true } })
      .then(() => refreshMe())
      .catch(() => undefined);
  }, [printed, mayMark, refreshMe]);
  const [branchId, setBranchId] = useState("all");
  // On a phone the sheet is shown smaller, to fit; it always prints at A4.
  const [fit, setFit] = useState(1);
  const measure = useCallback((box: HTMLDivElement | null) => {
    if (!box || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() =>
      setFit(Math.min(1, box.clientWidth / A4_WIDTH)),
    );
    watch.observe(box);
    return () => watch.disconnect();
  }, []);
  if (!me?.gym) return null;
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const url = `${origin}/${me.gym.slug}${branchId === "all" ? "" : `?b=${branchId}`}`;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3 print:hidden">
        {branches.length > 1 && (
          <div className="w-60">
            <Select
              label={t("sale.branch")}
              value={branchId}
              onChange={setBranchId}
              options={[
                { value: "all", label: t("extendAll.allBranches") },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          </div>
        )}
        <Button onClick={() => window.print()}>{t("card.print")}</Button>
      </div>
      <div ref={measure}>
        <div
          className="mx-auto flex flex-col items-center justify-center gap-8 bg-white p-12 text-center [zoom:var(--fit)] print:[zoom:1]"
          style={{ width: "210mm", minHeight: "297mm", ["--fit" as string]: fit }}
        >
          {me.gym.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={me.gym.logo_url} alt="" className="h-40 object-contain" />
          )}
          <h1 className="text-5xl font-bold">{me.gym.name}</h1>
          <p className="text-3xl">{t("poster.scan")}</p>
          <QrCode value={url} size={420} label={t("poster.qr")} />
          <p className="text-xl text-slate-600">{url.replace(/^https?:\/\//, "")}</p>
          <p className="text-lg text-slate-500">{t("poster.help")}</p>
        </div>
      </div>
    </div>
  );
}
