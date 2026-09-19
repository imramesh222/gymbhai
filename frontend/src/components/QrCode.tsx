"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

/** A QR code as inline SVG: crisp at any size, and printable. */
export function QrCode({
  value,
  size = 240,
  label,
}: {
  value: string;
  size?: number;
  label: string;
}) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    let cancelled = false;
    QRCode.toString(value, { type: "svg", margin: 1, errorCorrectionLevel: "M" })
      .then((result) => {
        if (!cancelled) setSvg(result);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [value]);
  return (
    <div
      role="img"
      aria-label={label}
      data-qr-value={value}
      style={{ width: size, height: size }}
      className="bg-white [&>svg]:h-full [&>svg]:w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
