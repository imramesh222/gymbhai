"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { t, type MessageKey } from "@/i18n";
import type { AppClass, AppClasses } from "@shared/types";
import { dayName } from "@shared/accessHours";
import { classColor } from "@shared/classColors";
import { inNepal } from "@shared/door/offline";
import { errorMessage } from "@/lib/api";
import { addDays, formatDate, todayInNepal } from "@/lib/dates";
import { newIdempotencyKey } from "@/lib/idempotency";
import { useLive } from "@/lib/live";
import { memberApi } from "@/lib/memberApi";
import { useMember } from "@/lib/memberSession";
import { useLoad } from "@/lib/useLoad";

const HOUR = 60 * 60 * 1000;

/**
 * Classes (PLAN.md §19.4): the week's classes at their branch, places left,
 * and theirs. Book, join the waitlist, or cancel; a double tap books once.
 */
export default function ClassesPage() {
  const { me } = useMember();
  const today = todayInNepal();
  const [from, setFrom] = useState(today);
  const week = useLoad(() => memberApi.classes(from), [from]);
  const [shown, setShown] = useState<AppClasses | null>(null);
  // Places taken by others, a waitlist place given to them.
  useLive(["class", "member"], () => {
    setShown(null);
    week.reload();
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  // One key per class until it books: a retry after no signal is the same tap.
  const keys = useRef(new Map<string, string>());
  const [now] = useState(() => Date.now());

  if (!me) return null;
  const data = shown ?? week.data;
  // Another week: what the last booking answered is for this one.
  const showWeek = (day: string) => {
    setShown(null);
    setFrom(day);
  };
  const display = me.gym.date_display;

  async function act(id: string, action: () => Promise<AppClasses>) {
    setPending(id);
    setError(null);
    try {
      setShown(await action());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  const book = (c: AppClass) =>
    act(c.id, async () => {
      const key = keys.current.get(c.id) ?? newIdempotencyKey();
      keys.current.set(c.id, key);
      const after = await memberApi.bookClass(c.id, key);
      keys.current.delete(c.id);
      return after;
    });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("app.classes.title")}</h1>
      <div className="flex gap-2">
        <Button
          variant={from === today ? "primary" : "secondary"}
          size="sm"
          onClick={() => showWeek(today)}
        >
          {t("app.classes.thisWeek")}
        </Button>
        <Button
          variant={from !== today ? "primary" : "secondary"}
          size="sm"
          onClick={() => showWeek(addDays(today, 7))}
        >
          {t("app.classes.nextWeek")}
        </Button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {week.error && <Notice tone="error">{week.error}</Notice>}
      {!data ? (
        !week.error && <p className="text-sm text-slate-500">{t("common.loading")}</p>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {t("app.classes.lateCancel", { hours: data.cancel_hours })}
          </p>
          {data.no_shows > 0 && (
            <p className="text-sm font-medium text-amber-800">
              {t("app.classes.noShows", { count: data.no_shows })}
            </p>
          )}
          {data.classes.length === 0 && (
            <p className="rounded-2xl bg-surface p-4 text-sm text-slate-600 ring-1 ring-hairline">
              {t("app.classes.none")}
            </p>
          )}
          {byDay(data.classes).map(([day, classes]) => (
            <section key={day} className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-700">
                {dayName(inNepal(Date.parse(`${day}T06:00:00+05:45`)).weekday)},{" "}
                {formatDate(day, display)}
              </h2>
              {classes.map((c) => (
                <ClassCard
                  key={c.id}
                  gymClass={c}
                  rules={data}
                  now={now}
                  busy={pending === c.id}
                  onBook={() => void book(c)}
                  onCancel={() =>
                    c.booking_id &&
                    void act(c.id, () => memberApi.cancelClassBooking(c.booking_id!))
                  }
                />
              ))}
            </section>
          ))}
        </>
      )}
    </div>
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
  busy,
  onBook,
  onCancel,
}: {
  gymClass: AppClass;
  rules: AppClasses;
  now: number;
  busy: boolean;
  onBook: () => void;
  onCancel: () => void;
}) {
  const starts = Date.parse(c.starts_at);
  const opens = starts - rules.booking_days * 24 * HOUR;
  const closes = starts - rules.closes_minutes * 60 * 1000;
  const time = inNepal(starts).time;

  let status: string;
  let action: React.ReactNode = null;
  if (c.cancelled) status = t("app.classes.cancelled");
  else if (c.mine === "booked") status = t("app.classes.booked");
  else if (c.mine === "waitlist") status = t("app.classes.onWaitlist");
  else if (c.places_left > 0)
    status = t("app.classes.placesLeft", { count: c.places_left });
  else status = t("app.classes.full", { count: c.waiting });

  if (c.cancelled) {
    action = null;
  } else if (c.mine) {
    action =
      starts > now ? (
        <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
          {t("app.classes.cancel")}
        </Button>
      ) : null;
  } else if (c.blocked) {
    action = (
      <span className="text-xs text-slate-500">
        {t(`app.classes.blocked.${c.blocked}` as MessageKey)}
      </span>
    );
  } else if (now < opens) {
    action = (
      <span className="text-xs text-slate-500">
        {t("app.classes.notOpen", { days: rules.booking_days })}
      </span>
    );
  } else if (now > closes) {
    action = <span className="text-xs text-slate-500">{t("app.classes.closed")}</span>;
  } else {
    action = (
      <Button size="sm" onClick={onBook} disabled={busy}>
        {c.places_left > 0 ? t("app.classes.book") : t("app.classes.joinWaitlist")}
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline">
      <div className="w-12 shrink-0 text-center">
        <p className="font-semibold tabular-nums">{time}</p>
      </div>
      <span
        aria-hidden
        className="size-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: classColor(c.color) }}
      />
      <div className="min-w-0 flex-1">
        <p
          className={`font-semibold ${c.cancelled ? "text-slate-400 line-through" : ""}`}
        >
          {c.type_name}
        </p>
        <p className="text-xs text-slate-500">
          {c.instructor_name &&
            `${t("app.classes.with", { name: c.instructor_name })} · `}
          {status}
        </p>
      </div>
      <div className="shrink-0">{action}</div>
    </div>
  );
}
