import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Pressable, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { t, type Locale } from "@shared/i18n";

import { apiUrl } from "@/lib/config";
import { useLocale } from "@/lib/locale";
import { colors, deepen, radius, space } from "@/lib/theme";

import { useBrand } from "./brand";
import { Txt } from "./ui";

/** The gym's logo, or its first letter on its colour. */
export function GymLogo({
  name,
  logoUrl,
  size = 44,
  onDark = false,
}: {
  name: string;
  logoUrl: string | null;
  size?: number;
  onDark?: boolean;
}) {
  const brand = useBrand();
  if (logoUrl) {
    return (
      <Image
        source={{ uri: apiUrl(logoUrl) }}
        contentFit="contain"
        accessibilityIgnoresInvertColors
        style={{
          width: size,
          height: size,
          borderRadius: size * 0.28,
          backgroundColor: "#ffffff",
          padding: 4,
        }}
      />
    );
  }
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.28,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: onDark ? "rgba(255,255,255,0.18)" : brand,
      }}
    >
      <Txt weight="bold" size={size * 0.42} color="#ffffff">
        {name.trim()[0]?.toUpperCase() ?? "G"}
      </Txt>
    </View>
  );
}

/**
 * The top of the signed-in app: the gym's colour, deepened towards the
 * corner, its logo and name, and who is signed in.
 */
export function GymHeader({
  name,
  logoUrl,
  memberName,
}: {
  name: string;
  logoUrl: string | null;
  memberName?: string;
}) {
  const brand = useBrand();
  const insets = useSafeAreaInsets();
  return (
    <LinearGradient
      colors={[brand, deepen(brand)]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{
        paddingTop: insets.top + space(3),
        paddingBottom: space(5),
        paddingHorizontal: space(5),
        borderBottomLeftRadius: radius.xl,
        borderBottomRightRadius: radius.xl,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}>
        <GymLogo name={name} logoUrl={logoUrl} size={42} onDark />
        <View style={{ flex: 1 }}>
          <Txt
            weight="semibold"
            size={18}
            color="#ffffff"
            numberOfLines={1}
            accessibilityRole="header"
          >
            {name}
          </Txt>
          {memberName ? (
            <Txt size={14} color="rgba(255,255,255,0.75)" numberOfLines={1}>
              {memberName}
            </Txt>
          ) : null}
        </View>
      </View>
    </LinearGradient>
  );
}

/** English / नेपाली, before signing in (PLAN.md §16.6). */
export function LanguageSwitch() {
  const { locale, choose } = useLocale();
  const options: { value: Locale; label: string }[] = [
    { value: "en", label: "English" },
    { value: "ne", label: "नेपाली" },
  ];
  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={t("language.title")}
      style={{
        flexDirection: "row",
        alignSelf: "center",
        backgroundColor: colors.track,
        borderRadius: 999,
        padding: 3,
      }}
    >
      {options.map((option) => {
        const selected = option.value === locale;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            onPress={() => choose(option.value)}
            style={{
              minHeight: 40,
              minWidth: 92,
              paddingHorizontal: space(4),
              borderRadius: 999,
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: selected ? colors.surface : "transparent",
            }}
          >
            <Txt
              weight={selected ? "semibold" : "regular"}
              size={14}
              color={colors.ink}
            >
              {option.label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}
