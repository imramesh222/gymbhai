/**
 * Going away? Ask the gym to pause the membership (PLAN.md §16.3, 8.6): when
 * from, for how long, and why. The gym's answer arrives live.
 *
 * Dates are chosen by stepping, not with the phone's date picker: that only
 * knows the AD calendar, and many gyms count and show dates in BS.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { addDays, formatDate, todayInNepal } from "@shared/dates";
import { t } from "@shared/i18n";

import { Screen } from "@/components/Screen";
import { Stepper } from "@/components/Stepper";
import {
  ActionButton,
  Card,
  Field,
  Notice,
  Spinner,
  Title,
  Txt,
} from "@/components/ui";
import { useLatestFreeze, useMe } from "@/lib/hooks";
import { memberApi } from "@/lib/memberApi";
import { keys } from "@/lib/query";
import { useSlug } from "@/lib/session";
import { colors, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

export default function Freeze() {
  const slug = useSlug();
  const queryClient = useQueryClient();
  const me = useMe().data;
  const latest = useLatestFreeze();
  const today = todayInNepal();
  const [from, setFrom] = useState(addDays(today, 1));
  const [days, setDays] = useState(14);
  const [reason, setReason] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.freeze(slug) });
  const ask = useAction(
    (key: string, body: { from_date: string; to_date: string; reason: string }) =>
      memberApi.askToFreeze(body, key),
    { onSuccess: () => void refresh() },
  );
  const withdraw = useAction(
    (key: string, id: string) => memberApi.withdrawFreeze(id, key),
    {
      onSuccess: () => void refresh(),
    },
  );

  if (!me || latest.data === undefined) return <Spinner />;
  const display = me.gym.date_display;
  const last = latest.data;
  const to = addDays(from, days - 1);

  if (last?.status === "pending") {
    return (
      <Screen onRefresh={refresh}>
        <Card
          style={{ gap: space(3), alignItems: "center", paddingVertical: space(8) }}
        >
          <Title style={{ textAlign: "center" }}>{t("app.freeze.waiting")}</Title>
          <Txt color={colors.muted}>
            {formatDate(last.from_date, display)} → {formatDate(last.to_date, display)}
          </Txt>
          <ActionButton
            action={withdraw}
            args={[last.id]}
            variant="secondary"
            label={t("app.renew.withdraw")}
            style={{ alignSelf: "stretch" }}
          />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen onRefresh={refresh}>
      <Txt color={colors.muted}>{t("app.freeze.help")}</Txt>
      {last?.status === "approved" ? (
        <Notice tone="success">
          {t("app.freeze.approved", {
            from: formatDate(last.from_date, display),
            to: formatDate(last.to_date, display),
          })}
        </Notice>
      ) : null}
      {last?.status === "rejected" ? (
        <Notice tone="warning">
          {t("app.freeze.rejected", { reason: last.reject_reason ?? "" })}
        </Notice>
      ) : null}
      <Card style={{ gap: space(4) }}>
        <Stepper
          label={t("app.freeze.from")}
          value={formatDate(from, display)}
          canLess={from > addDays(today, 1)}
          onLess={() => setFrom(addDays(from, -1))}
          onMore={() => setFrom(addDays(from, 1))}
        />
        <Stepper
          label={t("mobile.freeze.howLong")}
          value={t("app.freeze.days", { count: days })}
          canLess={days > 1}
          onLess={() => setDays(days - 1)}
          onMore={() => setDays(days + 1)}
        />
        <Txt size={14} color={colors.muted}>
          {t("app.freeze.to")}: {formatDate(to, display)}
        </Txt>
        <Field
          label={t("app.freeze.reason")}
          value={reason}
          onChangeText={setReason}
          multiline
        />
        <ActionButton
          action={ask}
          args={[{ from_date: from, to_date: to, reason: reason.trim() }]}
          label={t("app.freeze.send")}
          disabled={!reason.trim()}
        />
      </Card>
    </Screen>
  );
}
