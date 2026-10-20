"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { ProgressView } from "@/components/progress/ProgressView";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Checkbox, Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import type { Progress, ProgressPhoto } from "@shared/types";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { newIdempotencyKey } from "@/lib/idempotency";
import { shrinkImage } from "@/lib/image";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

type Pose = ProgressPhoto["pose"];
const POSES: Pose[] = ["front", "side", "back"];

/**
 * Your progress (PLAN.md §19.5): weight and measurements over time, and
 * photos only you see, unless you let your trainer see one.
 */
export default function ProgressPage() {
  const { me } = useMember();
  const loaded = useLoad(() => memberApi.progress(), []);
  const [shown, setShown] = useState<Progress | null>(null);
  if (!me) return null;
  const progress = shown ?? loaded.data;
  if (loaded.error) return <Notice tone="error">{loaded.error}</Notice>;
  if (!progress) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const display = me.gym.date_display;
  const date = (iso: string) => formatDate(iso, display);
  return (
    <div className="space-y-4">
      <ProgressView
        progress={progress}
        display={display}
        date={date}
        mayChange={() => true}
        onSave={async (input, entry) =>
          setShown(
            entry
              ? await memberApi.updateProgress(entry.id, input)
              : await memberApi.recordProgress(input, newIdempotencyKey()),
          )
        }
        onDelete={async (entry) => setShown(await memberApi.deleteProgress(entry.id))}
        onHeight={async (height) => setShown(await memberApi.setHeight(height))}
      />
      <Photos photos={progress.photos} date={date} onChanged={setShown} />
    </div>
  );
}

function Photos({
  photos,
  date,
  onChanged,
}: {
  photos: ProgressPhoto[];
  date: (iso: string) => string;
  onChanged: (progress: Progress) => void;
}) {
  const confirm = useConfirm();
  const input = useRef<HTMLInputElement>(null);
  const [pose, setPose] = useState<Pose>("front");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const days = [...new Set(photos.map((p) => p.taken_on))];
  const [compare, setCompare] = useState<{
    from: string;
    to: string;
    pose: Pose;
  } | null>(null);

  async function run(action: () => Promise<Progress>) {
    setError(null);
    setPending(true);
    try {
      onChanged(await action());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  const photoOf = (day: string, which: Pose) =>
    photos.find((p) => p.taken_on === day && p.pose === which);

  return (
    <section className="space-y-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
      <h2 className="font-semibold">{t("progress.photos")}</h2>
      <p className="text-sm text-slate-600">{t("progress.photosHelp")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-36">
          <Select<Pose>
            label={t("progress.addPhoto")}
            value={pose}
            onChange={setPose}
            options={POSES.map((p) => ({ value: p, label: t(`progress.pose.${p}`) }))}
          />
        </div>
        <Button onClick={() => input.current?.click()} disabled={pending}>
          {pending ? t("common.saving") : t("progress.addPhoto")}
        </Button>
        <input
          ref={input}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file)
              void run(async () =>
                memberApi.addProgressPhoto(await shrinkImage(file, 1600), pose),
              );
          }}
        />
      </div>
      {error && <Notice tone="error">{error}</Notice>}

      {days.length >= 2 && (
        <div className="space-y-2">
          {compare ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                {(["from", "to"] as const).map((side) => (
                  <Select
                    key={side}
                    label={side === "from" ? "←" : "→"}
                    value={compare[side]}
                    onChange={(day) => setCompare({ ...compare, [side]: day })}
                    options={days.map((d) => ({ value: d, label: date(d) }))}
                  />
                ))}
                <Select<Pose>
                  label={t("progress.addPhoto")}
                  value={compare.pose}
                  onChange={(which) => setCompare({ ...compare, pose: which })}
                  options={POSES.map((p) => ({
                    value: p,
                    label: t(`progress.pose.${p}`),
                  }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[compare.from, compare.to].map((day, i) => {
                  const photo = photoOf(day, compare.pose);
                  return (
                    <figure key={`${i}-${day}`} className="space-y-1">
                      {photo ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={photo.url}
                          alt={`${t(`progress.pose.${photo.pose}`)}, ${date(day)}`}
                          className="aspect-[3/4] w-full rounded-lg object-cover"
                        />
                      ) : (
                        <div className="aspect-[3/4] w-full rounded-lg bg-slate-100" />
                      )}
                      <figcaption className="text-center text-xs text-slate-500">
                        {date(day)}
                      </figcaption>
                    </figure>
                  );
                })}
              </div>
            </>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setCompare({ from: days[days.length - 1], to: days[0], pose: "front" })
              }
            >
              {t("progress.compare")}
            </Button>
          )}
        </div>
      )}

      <ul className="grid grid-cols-2 gap-3">
        {photos.map((photo) => (
          <li key={photo.id} className="space-y-1">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photo.url}
              alt={`${t(`progress.pose.${photo.pose}`)}, ${date(photo.taken_on)}`}
              className="aspect-[3/4] w-full rounded-lg object-cover ring-1 ring-hairline"
            />
            <p className="text-xs text-slate-500">
              {t(`progress.pose.${photo.pose}`)} · {date(photo.taken_on)}
            </p>
            <Checkbox
              label={t("progress.share")}
              checked={photo.shared}
              onChange={(shared) =>
                void run(() => memberApi.shareProgressPhoto(photo.id, shared))
              }
            />
            <button
              type="button"
              className="text-xs font-medium text-red-700 hover:underline"
              onClick={async () =>
                (await confirm({
                  title: t("progress.deletePhoto"),
                  message: t("progress.deletePhotoConfirm"),
                  confirmLabel: t("progress.deletePhoto"),
                  danger: true,
                })) && void run(() => memberApi.deleteProgressPhoto(photo.id))
              }
            >
              {t("progress.deletePhoto")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
