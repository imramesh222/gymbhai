/**
 * Your progress (PLAN.md §19.5): weight and measurements over time, and
 * photos only you see unless you let your trainer see one. Every change goes
 * through useAction: one tap is one save, however the network behaves.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Image, View } from "react-native";

import { addDays, formatDate, formatShort, todayInNepal } from "@shared/dates";
import { t } from "@shared/i18n";
import { bmi, changes, MEASURES, shown, stored, type Measure } from "@shared/progress";
import type { Progress, ProgressEntry, ProgressPhoto } from "@shared/types";

import { Screen } from "@/components/Screen";
import { Stepper } from "@/components/Stepper";
import {
  ActionButton,
  Button,
  Card,
  Field,
  Label,
  Notice,
  Spinner,
  Txt,
} from "@/components/ui";
import { WeightChart } from "@/components/WeightChart";
import { apiUrl } from "@/lib/config";
import { useMe, useProgress } from "@/lib/hooks";
import { pickImage } from "@/lib/images";
import { memberApi } from "@/lib/memberApi";
import { keys } from "@/lib/query";
import { useSlug } from "@/lib/session";
import { colors, radius, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

type Pose = ProgressPhoto["pose"];
const POSES: Pose[] = ["front", "side", "back"];

const signed = (value: number, unit: string) =>
  `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value)} ${unit}`;

function entryLine(entry: ProgressEntry): string {
  return MEASURES.filter((m) => entry[m.key] !== null)
    .map((m) =>
      m.key === "weight_g"
        ? `${shown(entry.weight_g, "kg")} kg`
        : `${t(m.label).replace(/ \(.*\)$/, "")} ${shown(entry[m.key], m.unit)} ${m.unit}`,
    )
    .join(" · ");
}

export default function ProgressScreen() {
  const slug = useSlug();
  const queryClient = useQueryClient();
  const progress = useProgress();
  const display = useMe().data?.gym.date_display ?? "both";
  const set = (fresh: Progress) => queryClient.setQueryData(keys.progress(slug), fresh);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: keys.progress(slug) });

  const remove = useAction(
    (key: string, id: string) => memberApi.deleteProgress(id, key),
    {
      onSuccess: set,
    },
  );

  const data = progress.data;
  if (!data)
    return progress.isError ? (
      <Notice tone="error">{t("errors.generic")}</Notice>
    ) : (
      <Spinner />
    );
  const weight = changes(data.entries, "weight_g");
  const latestBmi = bmi(weight?.latest ?? null, data.height_mm);
  const weights = [...data.entries]
    .filter((e) => e.weight_g !== null)
    .sort((a, b) => a.measured_on.localeCompare(b.measured_on));

  return (
    <Screen onRefresh={refresh}>
      <Card style={{ gap: space(2) }}>
        {weight ? (
          <>
            <Txt size={30} weight="bold" color={colors.ink}>
              {`${shown(weight.latest, "kg")} kg`}
            </Txt>
            {weight.sinceFirst !== null ? (
              <Txt size={14} color={colors.muted}>
                {t("progress.sinceFirst", {
                  change: signed(shown(weight.sinceFirst, "kg")!, "kg"),
                })}
              </Txt>
            ) : null}
            {latestBmi !== null ? (
              <Txt size={14} color={colors.muted}>
                {t("progress.bmi", { value: latestBmi })}
              </Txt>
            ) : null}
          </>
        ) : (
          <Txt color={colors.muted}>{t("progress.none")}</Txt>
        )}
      </Card>

      {weights.length >= 2 ? (
        <Card>
          <WeightChart
            title={t("progress.weightChart")}
            points={weights.map((e) => ({
              label: formatShort(e.measured_on, display),
              kg: shown(e.weight_g, "kg")!,
            }))}
          />
        </Card>
      ) : null}

      <NewCheck display={display} onSaved={set} />
      <Height value={data.height_mm} onSaved={set} />

      {data.entries.length > 0 ? (
        <Card style={{ gap: space(3) }}>
          {data.entries.map((entry) => (
            <View key={entry.id} style={{ gap: space(1) }}>
              <Txt weight="semibold">{formatDate(entry.measured_on, display)}</Txt>
              <Txt size={14}>{entryLine(entry)}</Txt>
              {entry.recorded_by_name ? (
                <Txt size={13} color={colors.faint}>
                  {t("progress.by", { name: entry.recorded_by_name })}
                </Txt>
              ) : null}
              <ActionButton
                action={remove}
                args={[entry.id]}
                variant="ghost"
                label={t("progress.delete")}
              />
            </View>
          ))}
        </Card>
      ) : null}

      <Photos photos={data.photos} display={display} onSaved={set} />
    </Screen>
  );
}

function NewCheck({
  display,
  onSaved,
}: {
  display: "ad" | "bs" | "both";
  onSaved: (fresh: Progress) => void;
}) {
  const today = todayInNepal();
  const [open, setOpen] = useState(false);
  const [day, setDay] = useState(today);
  const [values, setValues] = useState<Partial<Record<Measure, string>>>({});
  const save = useAction(
    (key: string, measuredOn: string) => {
      const body: Record<string, number | string | null> = { measured_on: measuredOn };
      for (const m of MEASURES) body[m.key] = stored(values[m.key] ?? "", m.unit);
      return memberApi.recordProgress(body, key);
    },
    {
      onSuccess: (fresh) => {
        onSaved(fresh);
        setValues({});
        setOpen(false);
      },
    },
  );
  const nothing = MEASURES.every((m) => stored(values[m.key] ?? "", m.unit) === null);
  if (!open) return <Button label={t("progress.add")} onPress={() => setOpen(true)} />;
  return (
    <Card style={{ gap: space(3) }}>
      <Stepper
        label={t("progress.date")}
        value={formatDate(day, display)}
        canLess
        canMore={day < today}
        onLess={() => setDay(addDays(day, -1))}
        onMore={() => setDay(addDays(day, 1))}
      />
      {MEASURES.map((m) => (
        <Field
          key={m.key}
          label={t(m.label)}
          value={values[m.key] ?? ""}
          onChangeText={(text) => setValues({ ...values, [m.key]: text })}
          keyboardType="decimal-pad"
        />
      ))}
      <ActionButton
        action={save}
        args={[day]}
        label={t("common.save")}
        disabled={nothing}
      />
    </Card>
  );
}

function Height({
  value,
  onSaved,
}: {
  value: number | null;
  onSaved: (fresh: Progress) => void;
}) {
  const [text, setText] = useState(value ? String(value / 10) : "");
  const save = useAction(
    (key: string, heightMm: number | null) => memberApi.setHeight(heightMm, key),
    { onSuccess: onSaved },
  );
  const next = stored(text, "cm");
  return (
    <Card style={{ gap: space(2) }}>
      <Field
        label={t("progress.height")}
        help={t("progress.heightHelp")}
        value={text}
        onChangeText={setText}
        keyboardType="decimal-pad"
      />
      {next !== value ? (
        <ActionButton
          action={save}
          args={[next]}
          variant="secondary"
          label={t("common.save")}
        />
      ) : null}
    </Card>
  );
}

function Photos({
  photos,
  display,
  onSaved,
}: {
  photos: ProgressPhoto[];
  display: "ad" | "bs" | "both";
  onSaved: (fresh: Progress) => void;
}) {
  const [pose, setPose] = useState<Pose>("front");
  const add = useAction(
    async (key: string, from: "gallery" | "camera", which: Pose) => {
      const file = await pickImage(from, "progress.jpg");
      return file ? memberApi.addProgressPhoto(file, which, key) : null;
    },
    { onSuccess: (fresh) => fresh && onSaved(fresh) },
  );
  const share = useAction(
    (key: string, id: string, shared: boolean) =>
      memberApi.shareProgressPhoto(id, shared, key),
    { onSuccess: onSaved },
  );
  const remove = useAction(
    (key: string, id: string) => memberApi.deleteProgressPhoto(id, key),
    { onSuccess: onSaved },
  );
  return (
    <Card style={{ gap: space(3) }}>
      <Label>{t("progress.photos")}</Label>
      <Txt size={14} color={colors.muted}>
        {t("progress.photosHelp")}
      </Txt>
      <View style={{ flexDirection: "row", gap: space(2) }}>
        {POSES.map((p) => (
          <Button
            key={p}
            label={t(`progress.pose.${p}`)}
            variant={pose === p ? "primary" : "secondary"}
            onPress={() => setPose(p)}
            style={{ flex: 1 }}
          />
        ))}
      </View>
      <ActionButton
        action={add}
        args={["camera", pose]}
        label={t("progress.addPhoto")}
      />
      {photos.map((photo) => (
        <View key={photo.id} style={{ gap: space(1.5) }}>
          <Image
            source={{ uri: apiUrl(photo.url) }}
            accessibilityLabel={`${t(`progress.pose.${photo.pose}`)}, ${formatDate(photo.taken_on, display)}`}
            style={{ width: "100%", aspectRatio: 3 / 4, borderRadius: radius.md }}
          />
          <Txt size={13} color={colors.faint}>
            {`${t(`progress.pose.${photo.pose}`)} · ${formatDate(photo.taken_on, display)}`}
          </Txt>
          <ActionButton
            action={share}
            args={[photo.id, !photo.shared]}
            variant="secondary"
            label={photo.shared ? `✓ ${t("progress.share")}` : t("progress.share")}
          />
          <ActionButton
            action={remove}
            args={[photo.id]}
            variant="ghost"
            label={t("progress.deletePhoto")}
          />
        </View>
      ))}
    </Card>
  );
}
