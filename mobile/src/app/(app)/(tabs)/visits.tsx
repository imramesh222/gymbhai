/** This month's visits as a calendar, live (PLAN.md §7, §17.5). */
import { View } from "react-native";

import { adMonths, todayInNepal } from "@shared/dates";
import { t, type MessageKey } from "@shared/i18n";

import { useBrand } from "@/components/brand";
import { Screen } from "@/components/Screen";
import { Card, Title, Txt } from "@/components/ui";
import { useVisits } from "@/lib/hooks";
import { colors, space } from "@/lib/theme";

const kathmanduDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kathmandu" });

const WEEK: MessageKey[] = [
  "days.sun",
  "days.mon",
  "days.tue",
  "days.wed",
  "days.thu",
  "days.fri",
  "days.sat",
];

export default function Visits() {
  const brand = useBrand();
  const month = todayInNepal().slice(0, 7);
  const visits = useVisits(month);
  const [year, number] = month.split("-").map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const firstWeekday = new Date(Date.UTC(year, number - 1, 1)).getUTCDay();
  const visited = new Set(
    (visits.data ?? []).map((v) => kathmanduDay.format(new Date(v.at))),
  );
  const today = todayInNepal();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];

  return (
    <Screen onRefresh={() => visits.refetch()}>
      <Title>{t("app.tab.visits")}</Title>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: space(2) }}>
        <Txt weight="bold" size={32} color={colors.ink}>
          {visited.size}
        </Txt>
        <Txt color={colors.faint}>
          {visited.size === 1
            ? t("app.visits.thisMonthOne")
            : t("app.visits.thisMonth")}
        </Txt>
      </View>
      <Card style={{ gap: space(2) }}>
        <Txt
          weight="semibold"
          color={colors.ink}
          style={{ textAlign: "center" }}
          accessibilityRole="header"
        >
          {adMonths()[number - 1]} {year}
        </Txt>
        <View
          style={{ flexDirection: "row" }}
          importantForAccessibility="no-hide-descendants"
        >
          {WEEK.map((key) => (
            <Txt
              key={key}
              accessible={false}
              size={12}
              weight="semibold"
              color={colors.faint}
              style={{ width: `${100 / 7}%`, textAlign: "center" }}
            >
              {t(key)}
            </Txt>
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {cells.map((day, i) => {
            const iso = day ? `${month}-${String(day).padStart(2, "0")}` : "";
            const went = day !== null && visited.has(iso);
            return (
              <View
                key={i}
                style={{ width: `${100 / 7}%`, aspectRatio: 1, padding: 3 }}
              >
                {day !== null ? (
                  <View
                    accessible
                    accessibilityLabel={went ? `${day} ✓` : String(day)}
                    style={{
                      flex: 1,
                      borderRadius: 999,
                      alignItems: "center",
                      justifyContent: "center",
                      backgroundColor: went ? brand : "transparent",
                      borderWidth: iso === today ? 1.5 : 0,
                      borderColor: brand,
                    }}
                  >
                    <Txt
                      size={14}
                      weight={went ? "semibold" : "regular"}
                      color={went ? "#ffffff" : colors.muted}
                    >
                      {day}
                    </Txt>
                  </View>
                ) : null}
              </View>
            );
          })}
        </View>
      </Card>
    </Screen>
  );
}
