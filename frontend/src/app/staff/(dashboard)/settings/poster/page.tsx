"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { QrCode } from "@/components/QrCode";
import { Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { branchesApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/useLoad";

/** The gym QR poster (§4.1): A4, logo, "Scan to see your membership". */
export default function PosterPage() {
  const { me } = useAuth();
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  const [branchId, setBranchId] = useState("all");
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
      <div
        className="mx-auto flex flex-col items-center justify-center gap-8 bg-white p-12 text-center"
        style={{ width: "210mm", minHeight: "297mm" }}
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
  );
}
