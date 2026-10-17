"use client";

import { Copy, Share2 } from "lucide-react";

import { Button } from "@/components/Button";
import { Card } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { subscriptionApi } from "@/lib/api";
import { formatAd } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

/**
 * Tell another gym (PLAN.md §16.5, 10.5): the link to share, and the gyms
 * that signed up with it. When one pays, a free month for both.
 */
export function ReferGyms() {
  const toast = useToast();
  const { data } = useLoad(() => subscriptionApi.referrals(), []);
  if (!data) return null;
  const text = t("refer.shareText", { link: data.link });
  return (
    <Card title={t("refer.title")}>
      <p className="text-sm text-slate-600">
        {t("refer.help", { months: data.free_months })}
      </p>
      <p className="mt-3 truncate rounded-xl bg-slate-50 px-3 py-2 font-mono text-sm ring-1 ring-hairline">
        {data.link}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={async () => {
            await navigator.clipboard.writeText(data.link);
            toast.success(t("refer.copied"));
          }}
        >
          <Copy className="size-4" aria-hidden />
          {t("refer.copy")}
        </Button>
        {typeof navigator !== "undefined" && "share" in navigator && (
          <Button
            variant="secondary"
            onClick={() => void navigator.share({ text }).catch(() => undefined)}
          >
            <Share2 className="size-4" aria-hidden />
            {t("receipt.share")}
          </Button>
        )}
      </div>
      {data.gyms.length > 0 && (
        <ul className="mt-4 divide-y divide-hairline text-sm">
          {data.gyms.map((g) => (
            <li key={g.name + g.joined_at} className="flex justify-between gap-3 py-2">
              <span className="font-medium">{g.name}</span>
              <span className="text-slate-500">
                {t(`refer.status.${g.status}` as MessageKey)} ·{" "}
                {formatAd(g.joined_at.slice(0, 10))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
