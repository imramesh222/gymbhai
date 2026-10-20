"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
import { Avatar } from "@/components/ui/Avatar";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, DateInput, Select, TextArea } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import { inNepal } from "@shared/door/offline";
import {
  classesApi,
  errorMessage,
  type ClassBooking,
  type ClassDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useIdempotencyKey } from "@/lib/idempotency";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

import { ColorDot } from "./ClassSettings";

export const timeOf = (iso: string) => inNepal(Date.parse(iso)).time;
export const dayOf = (iso: string) => inNepal(Date.parse(iso)).date;

/** One class (PLAN.md §19.4): who's coming, booking at the desk, who came,
 * and, for staff who manage classes, changing or cancelling it. */
export function ClassDialog({
  classId,
  onClose,
  onChanged,
}: {
  classId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { me, can } = useAuth();
  const { date } = useGymCalendar();
  const toast = useToast();
  const confirm = useConfirm();
  const { data, error, reload } = useLoad(() => classesApi.get(classId), [classId]);
  const [shown, setShown] = useState<ClassDetail | null>(null);
  const [mode, setMode] = useState<"roster" | "edit" | "cancel">("roster");
  const [actionError, setActionError] = useState<string | null>(null);
  // When it opened: good enough for "has it started" while it's open.
  const [now] = useState(() => Date.now());
  const gymClass = shown ?? data;
  // Booked from the app, or by another desk, while this is open.
  useLive(["class"], () => {
    setShown(null);
    reload();
  });

  async function run(action: () => Promise<ClassDetail>, done?: string) {
    setActionError(null);
    try {
      setShown(await action());
      if (done) toast.success(done);
      setMode("roster");
      onChanged();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  if (!gymClass)
    return (
      <Dialog open onClose={onClose} title={t("classes.title")}>
        {error ? <Notice tone="error">{error}</Notice> : <p>{t("common.loading")}</p>}
      </Dialog>
    );

  const started = Date.parse(gymClass.starts_at) <= now;
  const cancelled = gymClass.cancelled_at !== null;
  const mayMark =
    Date.parse(gymClass.starts_at) - 60 * 60 * 1000 <= now &&
    (can("classes.book") ||
      can("classes.manage") ||
      gymClass.instructor_id === me?.staff.id);
  const live = gymClass.bookings.filter((b) => b.status !== "cancelled");
  const title = `${gymClass.type_name} · ${date(dayOf(gymClass.starts_at))} ${timeOf(
    gymClass.starts_at,
  )}`;

  return (
    <Dialog open onClose={onClose} title={title}>
      <div className="space-y-4">
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <ColorDot color={gymClass.color} />
          {timeOf(gymClass.starts_at)}–{timeOf(gymClass.ends_at)}
          {gymClass.instructor_name && <span>· {gymClass.instructor_name}</span>}
          <span>
            ·{" "}
            {t("classes.booked", { booked: gymClass.booked, places: gymClass.places })}
          </span>
          {gymClass.waiting > 0 && (
            <span>· {t("classes.waiting", { count: gymClass.waiting })}</span>
          )}
        </p>
        {cancelled && (
          <Notice tone="warning">
            {t("classes.cancelledBecause", { reason: gymClass.cancel_reason ?? "" })}
          </Notice>
        )}
        {actionError && <Notice tone="error">{actionError}</Notice>}

        {mode === "edit" && (
          <EditClass
            gymClass={gymClass}
            onSave={(body) => run(() => classesApi.update(gymClass.id, body))}
            onBack={() => setMode("roster")}
          />
        )}
        {mode === "cancel" && (
          <CancelClass
            onSave={(reason, sms) =>
              run(() => classesApi.cancel(gymClass.id, reason, sms))
            }
            onBack={() => setMode("roster")}
          />
        )}
        {mode === "roster" && (
          <>
            <div>
              <h3 className="mb-1 text-sm font-semibold">{t("classes.roster")}</h3>
              {mayMark && live.length > 0 && (
                <p className="mb-1 text-xs text-slate-500">{t("classes.markHelp")}</p>
              )}
              {live.length === 0 ? (
                <p className="text-sm text-slate-500">{t("classes.empty")}</p>
              ) : (
                <ul className="divide-y divide-hairline">
                  {live.map((b) => (
                    <BookingRow
                      key={b.id}
                      booking={b}
                      mayMark={mayMark && b.status === "booked" && !cancelled}
                      mayCancel={can("classes.book") && !started && !cancelled}
                      onMark={(came) => run(() => classesApi.attended(b.id, came))}
                      onCancel={async () =>
                        (await confirm({
                          title: t("classes.cancelBooking"),
                          message: t("classes.cancelBookingConfirm", {
                            name: b.member_name,
                          }),
                          confirmLabel: t("classes.cancelBooking"),
                          danger: true,
                        })) && run(() => classesApi.cancelBooking(b.id))
                      }
                    />
                  ))}
                </ul>
              )}
            </div>
            {can("classes.book") && !started && !cancelled && (
              <BookMember
                exclude={live.map((b) => b.member_id)}
                onBook={(member, key) =>
                  run(async () => {
                    const after = await classesApi.book(gymClass.id, member.id, key);
                    const mine = after.bookings.find(
                      (b) => b.member_id === member.id && b.status !== "cancelled",
                    );
                    toast.success(
                      mine?.status === "waitlist"
                        ? t("classes.waitlisted")
                        : t("classes.bookedToast"),
                    );
                    return after;
                  })
                }
              />
            )}
            {can("classes.manage") && !cancelled && !started && (
              <div className="flex flex-wrap gap-2 border-t border-hairline pt-3">
                <Button variant="secondary" size="sm" onClick={() => setMode("edit")}>
                  {t("classes.editClass")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setMode("cancel")}>
                  {t("classes.cancelClass")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}

function BookingRow({
  booking,
  mayMark,
  mayCancel,
  onMark,
  onCancel,
}: {
  booking: ClassBooking;
  mayMark: boolean;
  mayCancel: boolean;
  onMark: (came: boolean) => void;
  onCancel: () => void;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      <Avatar name={booking.member_name} url={booking.photo_url} size="size-8" />
      <div className="min-w-0 flex-1 text-sm">
        <p className="truncate font-medium">{booking.member_name}</p>
        <p className="text-xs text-slate-500">
          {booking.member_code}
          {booking.status === "waitlist" && ` · ${t("classes.waitlist")}`}
          {booking.came && booking.attended === null && ` · ${t("classes.atDoor")}`}
        </p>
      </div>
      {mayMark && (
        <Checkbox
          label={t("classes.came")}
          checked={booking.came}
          onChange={(came) => onMark(came)}
        />
      )}
      {mayCancel && (
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t("classes.cancelBooking")}
        </Button>
      )}
    </li>
  );
}

function BookMember({
  exclude,
  onBook,
}: {
  exclude: string[];
  onBook: (member: Picked, key: string) => Promise<void>;
}) {
  const [member, setMember] = useState<Picked | null>(null);
  const booking = useIdempotencyKey();
  return (
    <div className="space-y-2 rounded-lg bg-slate-50 p-3">
      <MemberPicker
        label={t("classes.bookMember")}
        value={member}
        onChange={setMember}
        exclude={exclude}
      />
      <Button
        size="sm"
        disabled={!member}
        onClick={async () => {
          if (!member) return;
          const body = { member_id: member.id };
          await onBook(member, booking.keyFor(body));
          booking.succeeded();
          setMember(null);
        }}
      >
        {t("classes.book")}
      </Button>
    </div>
  );
}

function EditClass({
  gymClass,
  onSave,
  onBack,
}: {
  gymClass: ClassDetail;
  onSave: (body: Record<string, unknown>) => void;
  onBack: () => void;
}) {
  const { display } = useGymCalendar();
  const instructors = useLoad(() => classesApi.instructors(), []);
  const [form, setForm] = useState({
    day: dayOf(gymClass.starts_at),
    time: timeOf(gymClass.starts_at),
    places: String(gymClass.places),
    instructor_id: gymClass.instructor_id ?? "",
  });
  const [sms, setSms] = useState(false);
  const starts = `${form.day}T${form.time}:00+05:45`;
  const moving = Date.parse(starts) !== Date.parse(gymClass.starts_at);
  const told = gymClass.booked + gymClass.waiting;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const body: Record<string, unknown> = {};
        if (moving) {
          body.starts_at = starts;
          body.sms = sms;
        }
        if (Number(form.places) !== gymClass.places) body.places = Number(form.places);
        if ((form.instructor_id || null) !== gymClass.instructor_id)
          body.instructor_id = form.instructor_id || null;
        onSave(body);
      }}
      className="space-y-3"
    >
      <p className="text-xs text-slate-500">{t("classes.editClassHelp")}</p>
      <div className="grid grid-cols-2 gap-3">
        <DateInput
          label={t("classes.day")}
          value={form.day}
          onChange={(day) => setForm({ ...form, day })}
          display={display}
        />
        <Field
          label={t("classes.starts")}
          value={form.time}
          onChange={(time) => setForm({ ...form, time })}
          type="time"
        />
      </div>
      {moving && told > 0 && (
        <div className="space-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <p>{t("classes.moveTells", { count: told })}</p>
          <Checkbox label={t("classes.cancelSms")} checked={sms} onChange={setSms} />
        </div>
      )}
      <Field
        label={t("classes.places")}
        value={form.places}
        onChange={(places) => setForm({ ...form, places })}
        type="number"
        inputMode="numeric"
      />
      <Select
        label={t("classes.instructor")}
        value={form.instructor_id}
        onChange={(instructor_id) => setForm({ ...form, instructor_id })}
        options={[
          { value: "", label: t("classes.noInstructor") },
          ...(instructors.data ?? []).map((i) => ({ value: i.id, label: i.name })),
        ]}
      />
      <div className="flex gap-2">
        <Button type="submit">{t("common.save")}</Button>
        <Button variant="ghost" onClick={onBack}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function CancelClass({
  onSave,
  onBack,
}: {
  onSave: (reason: string, sms: boolean) => void;
  onBack: () => void;
}) {
  const [reason, setReason] = useState("");
  const [sms, setSms] = useState(false);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(reason, sms);
      }}
      className="space-y-3"
    >
      <TextArea
        label={t("classes.cancelReason")}
        value={reason}
        onChange={setReason}
        required
      />
      <Checkbox label={t("classes.cancelSms")} checked={sms} onChange={setSms} />
      <div className="flex gap-2">
        <Button type="submit" variant="danger">
          {t("classes.cancelClass")}
        </Button>
        <Button variant="ghost" onClick={onBack}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}
