/** The gym's notices, live: a new one appears as it's published (§17.5). */
import { formatDateTime } from "@shared/dates";
import { t } from "@shared/i18n";

import { Screen } from "@/components/Screen";
import { Card, Spinner, Txt } from "@/components/ui";
import { useMe, useNotices } from "@/lib/hooks";
import { colors, space } from "@/lib/theme";

export default function Notices() {
  const me = useMe().data;
  const notices = useNotices();
  if (!me || !notices.data) return <Spinner />;
  return (
    <Screen onRefresh={() => notices.refetch()}>
      {notices.data.length === 0 ? (
        <Txt color={colors.faint}>{t("notices.none")}</Txt>
      ) : null}
      {notices.data.map((n) => (
        <Card key={n.id} style={{ gap: space(1.5) }}>
          <Txt weight="semibold" color={colors.ink} accessibilityRole="header">
            {n.title}
          </Txt>
          <Txt size={15} color={colors.text} selectable>
            {n.body}
          </Txt>
          <Txt size={12} color={colors.faint}>
            {formatDateTime(n.published_at, me.gym.date_display)}
          </Txt>
        </Card>
      ))}
    </Screen>
  );
}
