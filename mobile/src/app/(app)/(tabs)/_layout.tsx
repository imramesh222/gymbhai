/** The five tabs, as in the web member app, under the gym's header. */
import { Tabs } from "expo-router";
import { View } from "react-native";

import { t, type MessageKey } from "@shared/i18n";

import { useBrand } from "@/components/brand";
import { GymHeader } from "@/components/GymParts";
import { Icon, type IconName } from "@/components/Icon";
import { OfflineBanner } from "@/components/Screen";
import { useMe } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { colors, fontFamily } from "@/lib/theme";

const TABS: { name: string; label: MessageKey; icon: IconName }[] = [
  { name: "home", label: "app.tab.home", icon: "home" },
  { name: "renew", label: "app.tab.renew", icon: "renew" },
  { name: "payments", label: "app.tab.payments", icon: "payments" },
  { name: "visits", label: "app.tab.visits", icon: "visits" },
  { name: "me", label: "app.tab.profile", icon: "profile" },
];

function Header() {
  const { gym } = useSession();
  const me = useMe().data;
  return (
    <View>
      <GymHeader
        name={me?.gym.name ?? gym?.name ?? ""}
        logoUrl={me?.gym.logo_url ?? gym?.logo_url ?? null}
        memberName={me?.name}
      />
      <OfflineBanner />
    </View>
  );
}

export default function TabsLayout() {
  const brand = useBrand();
  return (
    <Tabs
      screenOptions={{
        header: () => <Header />,
        tabBarActiveTintColor: brand,
        tabBarInactiveTintColor: colors.faint,
        tabBarLabelStyle: { fontFamily: fontFamily("medium"), fontSize: 11 },
        tabBarStyle: { borderTopColor: colors.hairline },
        sceneStyle: { backgroundColor: colors.canvas },
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: t(tab.label),
            tabBarAccessibilityLabel: t(tab.label),
            tabBarIcon: ({ color }) => <Icon name={tab.icon} color={color} />,
          }}
        />
      ))}
    </Tabs>
  );
}
