import { Modal, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { t } from "@shared/i18n";

import { colors, radius, space } from "@/lib/theme";

/**
 * A sheet that rises from the bottom over a dimmed screen, for a question the
 * member must answer (signing out). Always whole on screen, above the tab bar
 * and the home indicator, however far the page behind was scrolled. Tapping
 * the dim, or Android's back, is the same as cancelling.
 */
export function Sheet({
  visible,
  onClose,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      statusBarTranslucent
      navigationBarTranslucent
      onRequestClose={onClose}
    >
      <View style={{ flex: 1, justifyContent: "flex-end" }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("common.cancel")}
          onPress={onClose}
          style={[
            StyleSheet.absoluteFill,
            { backgroundColor: "rgba(15, 23, 42, 0.5)" },
          ]}
        />
        <View
          accessibilityViewIsModal
          style={{
            backgroundColor: colors.surface,
            borderTopLeftRadius: radius.xl,
            borderTopRightRadius: radius.xl,
            paddingHorizontal: space(5),
            paddingTop: space(3),
            paddingBottom: insets.bottom + space(5),
            gap: space(4),
          }}
        >
          <View
            style={{
              alignSelf: "center",
              width: 40,
              height: 4,
              borderRadius: 2,
              backgroundColor: colors.hairline,
            }}
          />
          {children}
        </View>
      </View>
    </Modal>
  );
}
