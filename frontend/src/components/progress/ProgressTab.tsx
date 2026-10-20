"use client";

import { useState } from "react";

import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import type { Progress } from "@shared/types";
import { progressApi } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";
import { newIdempotencyKey } from "@/lib/idempotency";
import { useLoad } from "@/lib/useLoad";

import { ProgressView } from "./ProgressView";

/** A member's progress on their profile (PLAN.md §19.5), for staff who record
 * progress: the checks, and the photos they shared, if this is their trainer. */
export function ProgressTab({ memberId }: { memberId: string }) {
  const { date, display } = useGymCalendar();
  const toast = useToast();
  const loaded = useLoad(() => progressApi.ofMember(memberId), [memberId]);
  const [shown, setShown] = useState<Progress | null>(null);
  const progress = shown ?? loaded.data;
  if (loaded.error) return <Notice tone="error">{loaded.error}</Notice>;
  if (!progress) return <ListSkeleton rows={2} />;

  const saved = (after: Progress) => {
    setShown(after);
    toast.success(t("progress.saved"));
  };
  return (
    <div className="space-y-4">
      <ProgressView
        progress={progress}
        display={display}
        date={date}
        // Staff change what staff recorded; the member's own stay theirs.
        mayChange={(entry) => entry.recorded_by_name !== null}
        onSave={async (input, entry) =>
          saved(
            entry
              ? await progressApi.update(entry.id, input)
              : await progressApi.record(memberId, input, newIdempotencyKey()),
          )
        }
        onDelete={async (entry) => setShown(await progressApi.remove(entry.id))}
        onHeight={async (height) =>
          saved(await progressApi.setHeight(memberId, height))
        }
      />
      {progress.photos.length > 0 && (
        <Card title={t("progress.sharedPhotos")}>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {progress.photos.map((photo) => (
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
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
