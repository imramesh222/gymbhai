"use client";

/**
 * Reads QR codes three ways (PLAN.md §4.3): the camera through the browser's
 * own BarcodeDetector, the camera through ZXing where that's missing, and a
 * USB or Bluetooth scanner, which types the code like a keyboard into a
 * hidden, always-focused input.
 */
import { useEffect, useRef, useState } from "react";

import { t } from "@/i18n";

interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}

declare global {
  interface Window {
    BarcodeDetector?: new (options: { formats: string[] }) => BarcodeDetectorLike;
  }
}

export function Scanner({
  onCode,
  paused = false,
  camera = true,
}: {
  onCode: (code: string) => void;
  paused?: boolean;
  camera?: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const typed = useRef<HTMLInputElement>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const onCodeRef = useRef(onCode);
  const pausedRef = useRef(paused);
  useEffect(() => {
    onCodeRef.current = onCode;
    pausedRef.current = paused;
  });

  // Camera.
  useEffect(() => {
    if (!camera) return;
    let stopped = false;
    let stream: MediaStream | null = null;
    let zxingControls: { stop: () => void } | null = null;
    let last = "";
    let lastAt = 0;

    function emit(code: string) {
      const now = Date.now();
      // The camera sees the same code many times a second.
      if (pausedRef.current || (code === last && now - lastAt < 4000)) return;
      last = code;
      lastAt = now;
      onCodeRef.current(code);
    }

    (async () => {
      try {
        if (window.BarcodeDetector) {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" },
          });
          if (stopped || !video.current) return;
          video.current.srcObject = stream;
          await video.current.play();
          const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
          const tick = async () => {
            if (stopped || !video.current) return;
            try {
              const found = await detector.detect(video.current);
              if (found[0]) emit(found[0].rawValue);
            } catch {
              // A frame that couldn't be read; try the next.
            }
            setTimeout(tick, 250);
          };
          void tick();
        } else {
          const { BrowserQRCodeReader } = await import("@zxing/browser");
          if (stopped || !video.current) return;
          const reader = new BrowserQRCodeReader();
          zxingControls = await reader.decodeFromVideoDevice(
            undefined,
            video.current,
            (result) => {
              if (result) emit(result.getText());
            },
          );
        }
      } catch {
        setCameraError(t("scanner.noCamera"));
      }
    })();

    return () => {
      stopped = true;
      zxingControls?.stop();
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [camera]);

  // USB scanners type fast and end with Enter; keep focus on the input.
  useEffect(() => {
    const keepFocus = () => {
      if (document.activeElement?.tagName !== "INPUT") typed.current?.focus();
    };
    keepFocus();
    const timer = setInterval(keepFocus, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="relative">
      {camera && (
        <video
          ref={video}
          muted
          playsInline
          className="aspect-square w-full rounded-2xl bg-black object-cover [transform:scaleX(-1)]"
        />
      )}
      {cameraError && (
        <p className="mt-2 text-center text-sm text-amber-700">{cameraError}</p>
      )}
      <input
        ref={typed}
        aria-label={t("scanner.typed")}
        autoComplete="off"
        className="absolute h-px w-px opacity-0"
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const value = e.currentTarget.value.trim();
            e.currentTarget.value = "";
            if (value && !pausedRef.current) onCodeRef.current(value);
          }
        }}
      />
    </div>
  );
}
