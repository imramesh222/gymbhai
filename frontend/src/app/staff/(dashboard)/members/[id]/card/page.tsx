"use client";

import { useParams } from "next/navigation";

import { Button } from "@/components/Button";
import { QrCode } from "@/components/QrCode";
import { t } from "@/i18n";
import { accessApi } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

/**
 * The printed card for members without a smartphone (§4.2): credit-card size,
 * with photo and member code. The scan result shows the photo, so the desk can
 * check the face on a shared card.
 */
export default function CardPage() {
  const { id } = useParams<{ id: string }>();
  const { data: card, reload } = useLoad(() => accessApi.card(id), [id]);
  if (!card) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  return (
    <div>
      <div className="mb-4 flex gap-2 print:hidden">
        <Button onClick={() => window.print()}>{t("card.print")}</Button>
        <Button
          variant="secondary"
          onClick={async () => {
            if (!window.confirm(t("card.reissueConfirm"))) return;
            await accessApi.reissueCard(id);
            reload();
          }}
        >
          {t("card.reissue")}
        </Button>
      </div>
      {/* 85.6 x 54 mm: a bank card. */}
      <div
        className="flex overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-hairline"
        style={{ width: "85.6mm", height: "54mm" }}
      >
        <div className="flex flex-1 flex-col justify-between p-[3mm]">
          <div className="flex items-center gap-2">
            {card.logo_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={card.logo_url}
                alt=""
                className="h-[8mm] w-[8mm] object-contain"
              />
            )}
            <p className="text-[9pt] font-bold leading-tight">{card.gym_name}</p>
          </div>
          {card.photo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={card.photo_url}
              alt=""
              className="h-[18mm] w-[18mm] rounded object-cover"
            />
          )}
          <div>
            <p className="text-[9pt] font-semibold leading-tight">{card.name}</p>
            <p className="text-[8pt] text-slate-600">{card.member_code}</p>
          </div>
        </div>
        <div className="flex items-center p-[2mm]">
          <QrCode value={card.card_code} size={150} label={t("card.qr")} />
        </div>
      </div>
    </div>
  );
}
