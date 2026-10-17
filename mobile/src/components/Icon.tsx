import type { ColorValue } from "react-native";
import Svg, { Path } from "react-native-svg";

/** Line icons on a 24px grid, the same drawings as the web member app. */
const PATHS = {
  home: "M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4v-5H9v5H5a1 1 0 0 1-1-1z",
  renew: "M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4",
  payments: "M3 8h18M3 8v9a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8M3 8l2-3h14l2 3M7 14h4",
  visits:
    "M8 3v3m8-3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z",
  profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20a7 7 0 0 1 14 0",
  scan: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20a2 2 0 0 0 4 0",
  chevron: "M9 6l6 6-6 6",
  close: "M6 6l12 12M18 6 6 18",
  download: "M12 4v11m0 0-4-4m4 4 4-4M5 19h14",
  camera:
    "M4 8a1 1 0 0 1 1-1h3l1.5-2h5L16 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7",
  image: "M4 5h16v14H4zM4 15l4-4 4 4 3-3 5 5M15.5 9.5h.01",
  share: "M12 15V4m0 0-4 4m4-4 4 4M6 12v7h12v-7",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 22,
  color = "currentColor",
  strokeWidth = 1.8,
}: {
  name: IconName;
  size?: number;
  color?: ColorValue;
  strokeWidth?: number;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      accessibilityElementsHidden
      importantForAccessibility="no"
    >
      <Path d={PATHS[name]} />
    </Svg>
  );
}
