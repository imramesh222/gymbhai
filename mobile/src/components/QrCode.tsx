import { create } from "qrcode";
import { useMemo } from "react";
import { View } from "react-native";
import Svg, { Path, Rect } from "react-native-svg";

/**
 * A QR code drawn as one SVG path: crisp at any size, no network, no canvas.
 * Error correction M and a one-module margin, as on the web (QrCode.tsx).
 */
export function QrCode({
  value,
  size,
  label,
  testID,
}: {
  value: string;
  size: number;
  label: string;
  testID?: string;
}) {
  const { path, count } = useMemo(() => {
    const { modules } = create(value, { errorCorrectionLevel: "M" });
    const n = modules.size;
    let d = "";
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        if (modules.get(x, y)) d += `M${x + 1} ${y + 1}h1v1h-1z`;
      }
    }
    return { path: d, count: n + 2 };
  }, [value]);
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      testID={testID}
      style={{ width: size, height: size }}
    >
      <Svg width={size} height={size} viewBox={`0 0 ${count} ${count}`}>
        <Rect width={count} height={count} fill="#ffffff" />
        <Path d={path} fill="#000000" />
      </Svg>
    </View>
  );
}
