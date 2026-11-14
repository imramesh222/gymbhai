"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, Select } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { dayName } from "@shared/accessHours";
import { classColor } from "@shared/classColors";
import {
  branchesApi,
  CLASS_COLORS,
  classesApi,
  errorMessage,
  gymApi,
  type Branch,
  type ClassColor,
  type ClassSlot,
  type ClassType,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/useLoad";

export function ColorDot({ color }: { color: string }) {
  return (
    <span
      aria-hidden
      className="inline-block size-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: classColor(color) }}
    />
  );
}

/** Settings → Classes (PLAN.md §19.4): the classes, the weekly timetable at
 * each branch, and the booking rules. */
export function ClassSettings() {
  const types = useLoad(() => classesApi.types(), []);
  const branches = useLoad(() => branchesApi.list(), []);
  const instructors = useLoad(() => classesApi.instructors(), []);
  return (
    <div className="space-y-4">
      <TypesCard types={types.data ?? []} error={types.error} reload={types.reload} />
      {(types.data?.length ?? 0) > 0 && (
        <TimetableCard
          types={(types.data ?? []).filter((k) => k.is_active)}
          branches={branches.data ?? []}
          instructors={instructors.data ?? []}
        />
      )}
      <RulesCard />
    </div>
  );
}

function TypesCard({
  types,
  error,
  reload,
}: {
  types: ClassType[];
  error: string | null;
  reload: () => void;
}) {
  const [editing, setEditing] = useState<ClassType | "new" | null>(null);
  return (
    <Card
      title={t("classes.types")}
      actions={
        <Button onClick={() => setEditing("new")}>{t("classes.addType")}</Button>
      }
    >
      <p className="mb-2 text-sm text-slate-600">{t("classes.typesHelp")}</p>
      {error && <Notice tone="error">{error}</Notice>}
      {types.length === 0 && <EmptyState title={t("classes.noTypes")} />}
      <ul className="divide-y divide-hairline">
        {types.map((kind) => (
          <li key={kind.id}>
            <button
              type="button"
              onClick={() => setEditing(kind)}
              className="flex w-full items-center gap-2 py-2 text-left text-sm hover:bg-slate-50"
            >
              <ColorDot color={kind.color} />
              <span className={kind.is_active ? "font-medium" : "text-slate-500"}>
                {kind.name}
              </span>
              <span className="text-slate-500">
                · {kind.minutes} min · {t("classes.places")} {kind.places}
                {!kind.is_active && ` · ${t("plans.hidden")}`}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {editing && (
        <TypeDialog
          kind={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

function TypeDialog({
  kind,
  onClose,
  onSaved,
}: {
  kind: ClassType | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: kind?.name ?? "",
    minutes: String(kind?.minutes ?? 60),
    places: String(kind?.places ?? 20),
    color: (kind?.color ?? "blue") as ClassColor,
    is_active: kind?.is_active ?? true,
  });
  const [error, setError] = useState<string | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      name: form.name,
      minutes: Number(form.minutes),
      places: Number(form.places),
      color: form.color,
      ...(kind ? { is_active: form.is_active } : {}),
    };
    try {
      if (kind) await classesApi.updateType(kind.id, body);
      else await classesApi.createType(body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Dialog
      open
      onClose={onClose}
      title={kind ? t("classes.editType") : t("classes.addType")}
    >
      <Form onSubmit={save} className="space-y-3">
        <Field
          label={t("classes.name")}
          value={form.name}
          onChange={(name) => setForm({ ...form, name })}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label={t("classes.minutes")}
            value={form.minutes}
            onChange={(minutes) => setForm({ ...form, minutes })}
            type="number"
            inputMode="numeric"
            required
          />
          <Field
            label={t("classes.places")}
            value={form.places}
            onChange={(places) => setForm({ ...form, places })}
            type="number"
            inputMode="numeric"
            required
          />
        </div>
        <Select<ClassColor>
          label={t("classes.color")}
          value={form.color}
          onChange={(color) => setForm({ ...form, color })}
          options={CLASS_COLORS.map((c) => ({
            value: c,
            label: t(`classes.color.${c}` as MessageKey),
          }))}
        />
        {kind && (
          <Checkbox
            label={t("classes.running")}
            checked={form.is_active}
            onChange={(is_active) => setForm({ ...form, is_active })}
          />
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </Form>
    </Dialog>
  );
}

function TimetableCard({
  types,
  branches,
  instructors,
}: {
  types: ClassType[];
  branches: Branch[];
  instructors: { id: string; name: string }[];
}) {
  const [branchId, setBranchId] = useState("");
  const branch = branchId || branches[0]?.id || "";
  const slots = useLoad(
    () => (branch ? classesApi.slots(branch) : Promise.resolve([])),
    [branch],
  );
  const [editing, setEditing] = useState<ClassSlot | "new" | null>(null);
  const typeOf = (id: string) => types.find((k) => k.id === id);
  const teacher = (id: string | null) => instructors.find((i) => i.id === id)?.name;
  return (
    <Card
      title={t("classes.timetable")}
      actions={
        <Button onClick={() => setEditing("new")}>{t("classes.addSlot")}</Button>
      }
    >
      <p className="mb-2 text-sm text-slate-600">{t("classes.timetableHelp")}</p>
      {branches.length > 1 && (
        <div className="mb-3 max-w-xs">
          <Select
            label={t("sale.branch")}
            value={branch}
            onChange={setBranchId}
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        </div>
      )}
      {slots.error && <Notice tone="error">{slots.error}</Notice>}
      {slots.data?.length === 0 && <EmptyState title={t("classes.noSlots")} />}
      <ul className="divide-y divide-hairline">
        {(slots.data ?? []).map((slot) => (
          <li key={slot.id}>
            <button
              type="button"
              onClick={() => setEditing(slot)}
              className="flex w-full items-center gap-2 py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className="w-24 shrink-0 font-medium">{dayName(slot.weekday)}</span>
              <span className="w-12 shrink-0 tabular-nums">{slot.starts}</span>
              <ColorDot color={typeOf(slot.type_id)?.color ?? "blue"} />
              <span className="font-medium">{typeOf(slot.type_id)?.name ?? "—"}</span>
              <span className="truncate text-slate-500">
                · {slot.minutes} min · {t("classes.places")} {slot.places}
                {" · "}
                {teacher(slot.instructor_id) ?? t("classes.noInstructor")}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {editing && (
        <SlotDialog
          slot={editing === "new" ? null : editing}
          branchId={branch}
          types={types}
          instructors={instructors}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            slots.reload();
          }}
        />
      )}
    </Card>
  );
}

function SlotDialog({
  slot,
  branchId,
  types,
  instructors,
  onClose,
  onSaved,
}: {
  slot: ClassSlot | null;
  branchId: string;
  types: ClassType[];
  instructors: { id: string; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const confirm = useConfirm();
  const [form, setForm] = useState({
    type_id: slot?.type_id ?? types[0]?.id ?? "",
    weekday: String(slot?.weekday ?? 0),
    starts: slot?.starts ?? "07:00",
    minutes: slot ? String(slot.minutes) : "",
    places: slot ? String(slot.places) : "",
    instructor_id: slot?.instructor_id ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  function save(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      type_id: form.type_id,
      weekday: Number(form.weekday),
      starts: form.starts,
      // Left empty: the class's own length and places.
      ...(form.minutes ? { minutes: Number(form.minutes) } : {}),
      ...(form.places ? { places: Number(form.places) } : {}),
      instructor_id: form.instructor_id || null,
    };
    return run(() =>
      slot
        ? classesApi.updateSlot(slot.id, body)
        : classesApi.createSlot({ ...body, branch_id: branchId }),
    );
  }
  return (
    <Dialog
      open
      onClose={onClose}
      title={slot ? t("classes.editSlot") : t("classes.addSlot")}
    >
      <Form onSubmit={save} className="space-y-3">
        <Select
          label={t("classes.name")}
          value={form.type_id}
          onChange={(type_id) => setForm({ ...form, type_id })}
          options={types.map((k) => ({ value: k.id, label: k.name }))}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label={t("classes.day")}
            value={form.weekday}
            onChange={(weekday) => setForm({ ...form, weekday })}
            options={[0, 1, 2, 3, 4, 5, 6].map((d) => ({
              value: String(d),
              label: dayName(d),
            }))}
          />
          <Field
            label={t("classes.starts")}
            value={form.starts}
            onChange={(starts) => setForm({ ...form, starts })}
            type="time"
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field
            label={t("classes.minutes")}
            value={form.minutes}
            onChange={(minutes) => setForm({ ...form, minutes })}
            type="number"
            inputMode="numeric"
            optional
            optionalLabel={t("common.optional")}
          />
          <Field
            label={t("classes.places")}
            value={form.places}
            onChange={(places) => setForm({ ...form, places })}
            type="number"
            inputMode="numeric"
            optional
            optionalLabel={t("common.optional")}
          />
        </div>
        <Select
          label={t("classes.instructor")}
          value={form.instructor_id}
          onChange={(instructor_id) => setForm({ ...form, instructor_id })}
          options={[
            { value: "", label: t("classes.noInstructor") },
            ...instructors.map((i) => ({ value: i.id, label: i.name })),
          ]}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
        {slot && (
          <Button
            variant="ghost"
            block
            onClick={async () =>
              (await confirm({
                title: t("classes.removeSlot"),
                message: t("classes.removeSlotConfirm"),
                confirmLabel: t("classes.removeSlot"),
                danger: true,
              })) &&
              void run(() => classesApi.updateSlot(slot.id, { is_active: false }))
            }
          >
            {t("classes.removeSlot")}
          </Button>
        )}
      </Form>
    </Dialog>
  );
}

function RulesCard() {
  const { me, can, refreshMe } = useAuth();
  const toast = useToast();
  const settings = me?.gym?.settings;
  const [form, setForm] = useState(() => ({
    class_booking_days: String(settings?.class_booking_days ?? 7),
    class_closes_minutes: String(settings?.class_closes_minutes ?? 30),
    class_cancel_hours: String(settings?.class_cancel_hours ?? 2),
    no_show_limit: String(settings?.no_show_limit ?? 0),
    no_show_block_days: String(settings?.no_show_block_days ?? 7),
  }));
  const [error, setError] = useState<string | null>(null);
  if (!can("classes.manage")) return null;
  async function save(event: React.FormEvent) {
    event.preventDefault();
    try {
      await gymApi.updateClassRules(
        Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v)])),
      );
      await refreshMe();
      setError(null);
      toast.success(t("common.saved"));
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const field = (key: keyof typeof form, label: MessageKey, help?: MessageKey) => (
    <Field
      label={t(label)}
      value={form[key]}
      onChange={(value) => setForm({ ...form, [key]: value })}
      type="number"
      inputMode="numeric"
      help={help ? t(help) : undefined}
    />
  );
  return (
    <Card title={t("classes.rules")}>
      <Form onSubmit={save} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          {field(
            "class_booking_days",
            "classes.bookingDays",
            "classes.bookingDaysHelp",
          )}
          {field(
            "class_closes_minutes",
            "classes.closesMinutes",
            "classes.closesMinutesHelp",
          )}
          {field(
            "class_cancel_hours",
            "classes.cancelHours",
            "classes.cancelHoursHelp",
          )}
          {field("no_show_limit", "classes.noShowLimit", "classes.noShowLimitHelp")}
          {field("no_show_block_days", "classes.noShowBlockDays")}
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit">{t("common.save")}</Button>
      </Form>
    </Card>
  );
}
