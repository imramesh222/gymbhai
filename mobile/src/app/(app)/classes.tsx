/**
 * Classes (PLAN.md §19.4): the week's classes at their branch, places left,
 * and theirs. Book, join the waitlist or cancel: one tap is one booking
 * however the network behaves (useAction, §17.4).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { View } from "react-native";

import { dayName } from "@shared/accessHours";
import { classColor } from "@shared/classColors";
import { addDays, formatDate, todayInNepal } from "@shared/dates";
import { inNepal } from "@shared/door/offline";
import { t, type MessageKey } from "@shared/i18n";
import type { AppClass, AppClasses } from "@shared/types";

import { Screen } from "@/components/Screen";
import {
  ActionButton,
  Button,
  Card,
  Label,
  Notice,
  Spinner,
  Txt,
} from "@/components/ui";
import { serverNow } from "@/lib/clock";
import { useClasses, useMe } from "@/lib/hooks";
import { memberApi } from "@/lib/memberApi";
import { useSlug } from "@/lib/session";
import { colors, space } from "@/lib/theme";
import { useAction, type Action } from "@/lib/useAction";

const HOUR = 60 * 60 * 1000;

export default function Classes() {
  const slug = useSlug();
  const queryClient = useQueryClient();
  const today = todayInNepal();
  const [from, setFrom] = useState(today);
  const week = useClasses(from);
  const display = useMe().data?.gym.date_display ?? "both";
  const [now] = useState(() => serverNow());

  const refresh = () => queryClient.invalidateQueries({ queryKey: [slug, "classes"] });
  const book = useAction(
    (key: string, classId: string) => memberApi.bookClass(classId, key),
    {
      onSuccess: () => void refresh(),
    },
  );
  const cancel = useAction(
    (key: string, bookingId: string) => memberApi.cancelClassBooking(bookingId, key),
    { onSuccess: () => void refresh() },
  );

  const data = week.data;
  return (
    <Screen onRefresh={refresh}>
      <View style={{ flexDirection: "row", gap: space(2) }}>
        <Button
          label={t("app.classes.thisWeek")}
          variant={from === today ? "primary" : "secondary"}
          onPress={() => setFrom(today)}
          style={{ flex: 1 }}
        />
        <Button
          label={t("app.classes.nextWeek")}
          variant={from !== today ? "primary" : "secondary"}
          onPress={() => setFrom(addDays(today, 7))}
          style={{ flex: 1 }}
        />
      </View>
      {!data ? (
        week.isError ? (
          <Notice tone="error">{t("errors.generic")}</Notice>
        ) : (
          <Spinner />
        )
      ) : (
        <>
          <Txt size={13} color={colors.faint}>
            {t("app.classes.lateCancel", { hours: data.cancel_hours })}
          </Txt>
          {data.no_shows > 0 ? (
            <Notice tone="warning">
              {t("app.classes.noShows", { count: data.no_shows })}
            </Notice>
          ) : null}
          {data.classes.length === 0 ? (
            <Card>
              <Txt color={colors.muted}>{t("app.classes.none")}</Txt>
            </Card>
          ) : null}
          {byDay(data.classes).map(([day, classes]) => (
            <View key={day} style={{ gap: space(2) }}>
              <Label>{`${dayName(inNepal(Date.parse(`${day}T06:00:00+05:45`)).weekday)}, ${formatDate(day, display)}`}</Label>
              {classes.map((c) => (
                <ClassCard
                  key={c.id}
                  gymClass={c}
                  rules={data}
                  now={now}
                  book={book}
                  cancel={cancel}
                />
              ))}
            </View>
          ))}
        </>
      )}
    </Screen>
  );
}

function byDay(classes: AppClass[]): [string, AppClass[]][] {
  const days = new Map<string, AppClass[]>();
  for (const c of classes) {
    const day = inNepal(Date.parse(c.starts_at)).date;
    days.set(day, [...(days.get(day) ?? []), c]);
  }
  return [...days.entries()];
}

function ClassCard({
  gymClass: c,
  rules,
  now,
  book,
  cancel,
}: {
  gymClass: AppClass;
  rules: AppClasses;
  now: number;
  book: Action<[string]>;
  cancel: Action<[string]>;
}) {
  const starts = Date.parse(c.starts_at);
  const opens = starts - rules.booking_days * 24 * HOUR;
  const closes = starts - rules.closes_minutes * 60 * 1000;

  let status: string;
  if (c.cancelled) status = t("app.classes.cancelled");
  else if (c.mine === "booked") status = t("app.classes.booked");
  else if (c.mine === "waitlist") status = t("app.classes.onWaitlist");
  else if (c.places_left > 0)
    status = t("app.classes.placesLeft", { count: c.places_left });
  else status = t("app.classes.full", { count: c.waiting });

  let action: React.ReactNode = null;
  if (c.cancelled) action = null;
  else if (c.mine && c.booking_id && starts > now)
    action = (
      <ActionButton
        action={cancel}
        args={[c.booking_id]}
        variant="secondary"
        label={t("app.classes.cancel")}
      />
    );
  else if (c.mine) action = null;
  else if (c.blocked)
    action = (
      <Txt size={13} color={colors.faint}>
        {t(`app.classes.blocked.${c.blocked}` as MessageKey)}
      </Txt>
    );
  else if (now < opens)
    action = (
      <Txt size={13} color={colors.faint}>
        {t("app.classes.notOpen", { days: rules.booking_days })}
      </Txt>
    );
  else if (now > closes)
    action = (
      <Txt size={13} color={colors.faint}>
        {t("app.classes.closed")}
      </Txt>
    );
  else
    action = (
      <ActionButton
        action={book}
        args={[c.id]}
        label={
          c.places_left > 0 ? t("app.classes.book") : t("app.classes.joinWaitlist")
        }
      />
    );

  return (
    <Card style={{ gap: space(2) }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}>
        <Txt weight="semibold">{inNepal(starts).time}</Txt>
        <View
          accessible={false}
          style={{
            width: 10,
            height: 10,
            borderRadius: 5,
            backgroundColor: classColor(c.color),
          }}
        />
        <View style={{ flex: 1 }}>
          <Txt
            weight="semibold"
            color={c.cancelled ? colors.faint : colors.ink}
            style={c.cancelled ? { textDecorationLine: "line-through" } : undefined}
          >
            {c.type_name}
          </Txt>
          <Txt size={13} color={colors.muted}>
            {c.instructor_name
              ? `${t("app.classes.with", { name: c.instructor_name })} · `
              : ""}
            {status}
          </Txt>
        </View>
      </View>
      {action}
    </Card>
  );
}
