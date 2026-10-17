/**
 * Me (PLAN.md §17.5): photo, email (a code to the new address first),
 * emergency contact, language, notifications, notices, switching gym and
 * signing out.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, View } from "react-native";

import { t, type Locale } from "@shared/i18n";
import type { MemberMe } from "@shared/types";

import { Icon } from "@/components/Icon";
import { PushSetting } from "@/components/PushPrompt";
import { Screen } from "@/components/Screen";
import {
  ActionButton,
  ActionStatus,
  Button,
  Card,
  ChoiceRow,
  Field,
  Label,
  LinkButton,
  Spinner,
  Txt,
} from "@/components/ui";
import { apiUrl } from "@/lib/config";
import { useMe } from "@/lib/hooks";
import { pickImage } from "@/lib/images";
import { memberApi } from "@/lib/memberApi";
import { keys } from "@/lib/query";
import { useSession, useSlug } from "@/lib/session";
import { colors, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

function useSetMe() {
  const slug = useSlug();
  const queryClient = useQueryClient();
  return (me: MemberMe) => queryClient.setQueryData(keys.me(slug), me);
}

function Photo({ me }: { me: MemberMe }) {
  const setMe = useSetMe();
  const change = useAction(
    async (_key: string, from: "gallery" | "camera") => {
      const file = await pickImage(from, "photo.jpg");
      return file ? memberApi.uploadPhoto(file) : null;
    },
    { onSuccess: (fresh) => fresh && setMe(fresh) },
  );
  return (
    <View style={{ gap: space(2) }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space(4) }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("app.profile.photo")}
          onPress={() =>
            Alert.alert(t("app.profile.photo"), undefined, [
              { text: t("mobile.photo.camera"), onPress: () => change.run("camera") },
              { text: t("mobile.photo.gallery"), onPress: () => change.run("gallery") },
              { text: t("common.cancel"), style: "cancel" },
            ])
          }
          style={{ width: 72, height: 72 }}
        >
          {me.photo_url ? (
            <Image
              source={{ uri: apiUrl(me.photo_url) }}
              style={{ width: 72, height: 72, borderRadius: 36 }}
            />
          ) : (
            <View
              style={{
                width: 72,
                height: 72,
                borderRadius: 36,
                backgroundColor: colors.track,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon name="camera" color={colors.faint} size={26} />
            </View>
          )}
        </Pressable>
        <View style={{ flex: 1 }}>
          <Txt weight="semibold" size={20} color={colors.ink}>
            {me.name}
          </Txt>
          <Txt size={14} color={colors.faint}>
            {me.member_code}
          </Txt>
        </View>
      </View>
      <Txt size={13} color={colors.faint}>
        {change.busy ? t("common.loading") : t("app.profile.photoHelp")}
      </Txt>
      <ActionStatus action={change} />
    </View>
  );
}

/** A new email: a code to it first, then it's theirs (§16.3, 8.5). */
function EmailChange({ onDone }: { onDone: () => void }) {
  const setMe = useSetMe();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const send = useAction(
    (_key: string, address: string) => memberApi.changeEmail(address),
    {
      onSuccess: () => setSent(true),
    },
  );
  const confirm = useAction(
    (key: string, address: string, digits: string) =>
      memberApi.confirmEmail(address, digits, key),
    {
      onSuccess: (fresh) => {
        setMe(fresh);
        onDone();
      },
    },
  );
  return (
    <View style={{ gap: space(3) }}>
      <Field
        label={t("app.profile.newEmail")}
        value={email}
        onChangeText={(value) => {
          setEmail(value);
          setSent(false);
        }}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
        autoCorrect={false}
      />
      {sent ? (
        <>
          <Txt size={14} color={colors.muted}>
            {t("app.profile.codeSent", { email })}
          </Txt>
          <Field
            label={t("app.signIn.code")}
            value={code}
            onChangeText={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
            keyboardType="number-pad"
            textContentType="oneTimeCode"
            maxLength={6}
          />
          <ActionButton
            action={confirm}
            args={[email.trim(), code]}
            label={t("app.profile.confirm")}
            disabled={code.length !== 6}
          />
        </>
      ) : (
        <ActionButton
          action={send}
          args={[email.trim()]}
          label={t("app.profile.sendCode")}
          disabled={!email.includes("@")}
        />
      )}
      <LinkButton label={t("common.cancel")} color={colors.faint} onPress={onDone} />
    </View>
  );
}

function EmergencyContact({ initial }: { initial: string | null }) {
  const setMe = useSetMe();
  const [value, setValue] = useState(initial ?? "");
  const [saved, setSaved] = useState(false);
  const save = useAction(
    (_key: string, contact: string | null) =>
      memberApi.updateMe({ emergency_contact: contact }),
    {
      onSuccess: (fresh) => {
        setMe(fresh);
        setSaved(true);
      },
    },
  );
  const dirty = value.trim() !== (initial ?? "");
  return (
    <View style={{ gap: space(2) }}>
      <Field
        label={t("app.profile.emergency")}
        help={t("app.profile.emergencyHelp")}
        value={value}
        onChangeText={(next) => {
          setValue(next);
          setSaved(false);
        }}
      />
      {saved && !dirty ? (
        <Txt size={14} color={colors.green}>
          {t("app.profile.saved")}
        </Txt>
      ) : null}
      {dirty ? (
        <ActionButton
          action={save}
          args={[value.trim() || null]}
          variant="secondary"
          label={t("common.save")}
        />
      ) : null}
    </View>
  );
}

/** Their own language, or the gym's (§16.6). */
function Language({ me }: { me: MemberMe }) {
  const setMe = useSetMe();
  const change = useAction(
    (_key: string, language: Locale | null) => memberApi.updateMe({ language }),
    { onSuccess: setMe },
  );
  const gymLanguage = me.language === "ne" && !me.own_language ? "नेपाली" : "English";
  const options: { value: Locale | null; label: string }[] = [
    {
      value: null,
      label: t("language.gymDefault", {
        language: me.own_language ? t("language.gyms") : gymLanguage,
      }),
    },
    { value: "en", label: "English" },
    { value: "ne", label: "नेपाली" },
  ];
  return (
    <Card style={{ gap: space(2) }}>
      <Label>{t("language.title")}</Label>
      {options.map((option) => (
        <ChoiceRow
          key={option.value ?? "gym"}
          selected={me.own_language === option.value}
          onPress={() => change.run(option.value)}
          accessibilityLabel={option.label}
        >
          <Txt>{option.label}</Txt>
        </ChoiceRow>
      ))}
      <ActionStatus action={change} />
    </Card>
  );
}

export default function Me() {
  const me = useMe();
  const { signOut, closeGym, gyms } = useSession();
  const [editingEmail, setEditingEmail] = useState(false);
  const out = useAction(() => signOut());
  if (!me.data) return <Spinner />;

  return (
    <Screen onRefresh={() => me.refetch()}>
      <Photo me={me.data} />

      <Card style={{ gap: space(4) }}>
        <View style={{ gap: space(1) }}>
          <Label>{t("member.phone")}</Label>
          <Txt>{me.data.phone}</Txt>
        </View>
        <View style={{ gap: space(1) }}>
          <Label>{t("member.email")}</Label>
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <Txt>{me.data.email ?? "—"}</Txt>
            {!editingEmail ? (
              <LinkButton
                label={t("app.profile.edit")}
                onPress={() => setEditingEmail(true)}
              />
            ) : null}
          </View>
        </View>
        {editingEmail ? <EmailChange onDone={() => setEditingEmail(false)} /> : null}
        <EmergencyContact initial={me.data.emergency_contact} />
        <Txt size={13} color={colors.faint}>
          {t("app.profile.readOnly")}
        </Txt>
      </Card>

      <Language me={me.data} />
      <PushSetting />

      <Card style={{ gap: space(1) }}>
        <LinkButton
          align="flex-start"
          label={t("app.notices")}
          onPress={() => router.push("/notices")}
        />
        {me.data.state.status === "active" ? (
          <LinkButton
            align="flex-start"
            label={t("app.freeze.title")}
            onPress={() => router.push("/freeze")}
          />
        ) : null}
        <LinkButton
          align="flex-start"
          label={gyms.length > 1 ? t("mobile.switchGym") : t("mobile.addGym")}
          onPress={() => void closeGym()}
        />
      </Card>

      <Button
        variant="secondary"
        label={t("common.signOut")}
        busy={out.busy}
        onPress={() =>
          Alert.alert(t("mobile.signOut.confirm"), t("mobile.signOut.help"), [
            { text: t("common.cancel"), style: "cancel" },
            {
              text: t("common.signOut"),
              style: "destructive",
              onPress: () => out.run(),
            },
          ])
        }
      />
    </Screen>
  );
}
