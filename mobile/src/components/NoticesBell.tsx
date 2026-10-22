import { router } from "expo-router";
import { Pressable, View } from "react-native";

import { t } from "@shared/i18n";

import { useMe } from "@/lib/hooks";
import { hasUnread, useNoticesSeen } from "@/lib/noticesSeen";
import { useSlug } from "@/lib/session";
import { colors } from "@/lib/theme";

import { Icon } from "./Icon";

/**
 * The gym's notices, top right on every tab (PLAN.md §17.5), with a red dot
 * while there's one this phone hasn't opened Notices for. A new notice
 * arrives live (§17.3), so the dot appears without a refresh.
 */
export function NoticesBell() {
  const slug = useSlug();
  const latest = useMe().data?.latest_notice?.published_at;
  const unread = hasUnread(latest, useNoticesSeen(slug));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={unread ? t("mobile.notices.new") : t("app.notices")}
      onPress={() => router.push("/notices")}
      hitSlop={6}
      testID="notices"
      style={({ pressed }) => ({
        width: 44,
        height: 44,
        borderRadius: 22,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: pressed ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.16)",
      })}
    >
      <Icon name="bell" color="#ffffff" size={22} />
      {unread ? (
        <View
          testID="notices-unread"
          style={{
            position: "absolute",
            top: 9,
            right: 10,
            width: 11,
            height: 11,
            borderRadius: 6,
            backgroundColor: colors.busy,
            borderWidth: 2,
            borderColor: "#ffffff",
          }}
        />
      ) : null}
    </Pressable>
  );
}
