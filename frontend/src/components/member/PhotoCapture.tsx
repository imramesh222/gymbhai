"use client";

import { Camera, ImageUp, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { t } from "@/i18n";
import { shrinkImage } from "@/lib/image";

/** The camera, live, in a dialog: Take photo, or Choose a file instead. */
function CameraDialog({
  onClose,
  onTaken,
}: {
  onClose: () => void;
  onTaken: (photo: Blob) => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      // No camera API (an old browser, or a page not served over HTTPS).
      Promise.resolve().then(() => setFailed(true));
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user", width: 640, height: 640 } })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((track) => track.stop());
        stream = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  function take() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    // A square from the middle: the card and the avatar are round or square.
    const side = Math.min(v.videoWidth, v.videoHeight);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = side;
    canvas
      .getContext("2d")
      ?.drawImage(
        v,
        (v.videoWidth - side) / 2,
        (v.videoHeight - side) / 2,
        side,
        side,
        0,
        0,
        side,
        side,
      );
    canvas.toBlob((blob) => blob && onTaken(blob), "image/jpeg", 0.85);
  }

  return (
    <Dialog open onClose={onClose} title={t("photo.title")}>
      <div className="space-y-4">
        {failed ? (
          <Notice>{t("photo.noCamera")}</Notice>
        ) : (
          <video
            ref={video}
            autoPlay
            playsInline
            muted
            className="aspect-square w-full rounded-xl bg-slate-900 object-cover"
          />
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          {!failed && (
            <Button type="button" block onClick={take}>
              <Camera className="size-4" aria-hidden />
              {t("photo.take")}
            </Button>
          )}
          <Button
            type="button"
            variant="secondary"
            block
            onClick={() => file.current?.click()}
          >
            <ImageUp className="size-4" aria-hidden />
            {t("photo.choose")}
          </Button>
        </div>
        <input
          ref={file}
          type="file"
          accept="image/*"
          capture="user"
          className="hidden"
          onChange={async (event) => {
            const chosen = event.target.files?.[0];
            if (chosen) onTaken(await shrinkImage(chosen));
          }}
        />
      </div>
    </Dialog>
  );
}

/**
 * A member's photo, taken at the desk (PLAN.md §16.2, 7.7): the printed card
 * relies on the desk seeing their face (§4.2). Shows the photo once taken.
 */
export function PhotoCapture({
  photo,
  onChange,
}: {
  photo: Blob | null;
  onChange: (photo: Blob | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    if (!photo) return;
    const url = URL.createObjectURL(photo);
    Promise.resolve().then(() => setPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  return (
    <div className="flex items-center gap-4">
      {photo && preview ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={preview}
          alt={t("photo.preview")}
          className="size-20 rounded-full object-cover ring-1 ring-hairline"
        />
      ) : (
        <span className="flex size-20 items-center justify-center rounded-full bg-slate-100 text-slate-500">
          <Camera className="size-7" aria-hidden />
        </span>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
          {photo ? (
            <RotateCcw className="size-4" aria-hidden />
          ) : (
            <Camera className="size-4" aria-hidden />
          )}
          {photo ? t("photo.retake") : t("photo.add")}
        </Button>
        {photo && (
          <Button type="button" variant="ghost" onClick={() => onChange(null)}>
            {t("photo.remove")}
          </Button>
        )}
      </div>
      {open && (
        <CameraDialog
          onClose={() => setOpen(false)}
          onTaken={(taken) => {
            setOpen(false);
            onChange(taken);
          }}
        />
      )}
    </div>
  );
}
