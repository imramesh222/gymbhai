/**
 * Weight over time (PLAN.md §19.5), as the dashboard draws it
 * (frontend/src/components/charts/LineChart.tsx): one series in brand blue,
 * a 2px line, the scale fitted to the values (a line encodes position, not
 * length), the latest value labelled at its end, recessive gridlines. No
 * legend: the title names the one series. The checks listed under it are its
 * table; a screen reader hears the first and latest values.
 */
import { useState } from "react";
import { View } from "react-native";
import Svg, { Circle, Line, Path, Text as SvgText } from "react-native-svg";

import { niceRange } from "@shared/niceRange";

import { Txt } from "./ui";
import { colors, space } from "@/lib/theme";

const SERIES = "#1d5fd1";
const GRID = "#e2e8f0";
const AXIS_TEXT = "#64748b";
const PAD = { top: 12, right: 64, bottom: 22, left: 36 };

export function WeightChart({
  title,
  points,
  height = 170,
}: {
  title: string;
  /** Oldest first: a label (a short date) and kilograms. */
  points: { label: string; kg: number }[];
  height?: number;
}) {
  const [width, setWidth] = useState(0);
  if (points.length < 2) return null;
  const values = points.map((p) => p.kg);
  const ticks = niceRange(Math.min(...values), Math.max(...values));
  const bottom = ticks[0];
  const top = ticks[ticks.length - 1];
  const plotW = Math.max(width - PAD.left - PAD.right, 1);
  const plotH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * plotW;
  const y = (kg: number) => PAD.top + plotH - ((kg - bottom) / (top - bottom)) * plotH;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.kg)}`).join("");
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <View style={{ gap: space(2) }}>
      <Txt weight="semibold" color={colors.ink}>
        {title}
      </Txt>
      <View
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        accessible
        accessibilityRole="image"
        accessibilityLabel={`${title}: ${first.kg} kg, ${first.label}; ${last.kg} kg, ${last.label}`}
      >
        {width > 0 ? (
          <Svg width={width} height={height}>
            {ticks.map((tick) => (
              <Line
                key={`grid-${tick}`}
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke={GRID}
                strokeWidth={1}
              />
            ))}
            {ticks.map((tick) => (
              <SvgText
                key={`tick-${tick}`}
                x={PAD.left - 6}
                y={y(tick) + 4}
                fontSize={11}
                fill={AXIS_TEXT}
                textAnchor="end"
              >
                {String(tick)}
              </SvgText>
            ))}
            <SvgText
              x={x(0)}
              y={height - 6}
              fontSize={11}
              fill={AXIS_TEXT}
              textAnchor="start"
            >
              {first.label}
            </SvgText>
            <SvgText
              x={x(points.length - 1)}
              y={height - 6}
              fontSize={11}
              fill={AXIS_TEXT}
              textAnchor="end"
            >
              {last.label}
            </SvgText>
            <Path
              d={line}
              fill="none"
              stroke={SERIES}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <Circle
              cx={x(points.length - 1)}
              cy={y(last.kg)}
              r={4}
              fill={SERIES}
              stroke="#ffffff"
              strokeWidth={2}
            />
            <SvgText
              x={x(points.length - 1) + 8}
              y={y(last.kg) + 4}
              fontSize={12}
              fontWeight="600"
              fill={colors.ink}
            >
              {`${last.kg} kg`}
            </SvgText>
          </Svg>
        ) : (
          <View style={{ height }} />
        )}
      </View>
    </View>
  );
}
