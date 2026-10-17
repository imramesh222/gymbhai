/**
 * Sign in (PLAN.md §17.5): mobile number or email, then the 6-digit code
 * (filled in from the SMS where the phone offers it), then "Who are you?"
 * when several members share the number.
 */
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";

import { t } from "@shared/i18n";
import type { MemberSignIn } from "@shared/types";

import { GymLogo, LanguageSwitch } from "@/components/GymParts";
import { Screen } from "@/components/Screen";
import {
  ActionStatus,
  Button,
  Card,
  Field,
  LinkButton,
  Title,
  Txt,
} from "@/components/ui";
import { memberApi } from "@/lib/memberApi";
import { useSession } from "@/lib/session";
import { colors, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

/** The server sends one code per 30 seconds however often it's asked (§17.2, 5). */
const RESEND_SECONDS = 30;

function useCountdown(from: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (from === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [from]);
  if (from === null) return 0;
  return Math.max(0, RESEND_SECONDS - Math.floor((now - from) / 1000));
}

export default function SignIn() {
  const { gym, closeGym, signedInWith } = useSession();
  const [who, setWho] = useState("");
  // The keypad: numbers for a mobile number, letters for an email.
  const [byEmail, setByEmail] = useState(false);
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [sentAt, setSentAt] = useState<number | null>(null);
  const [choose, setChoose] = useState<MemberSignIn["choose"]>(null);
  const wait = useCountdown(sentAt);
  const slug = gym?.slug ?? "";

  const target = () =>
    who.includes("@") ? { email: who.trim() } : { phone: who.trim() };

  const send = useAction((_key: string) => memberApi.requestCode(slug, target()), {
    onSuccess: (result) => {
      setSentTo(result.sent_to);
      setSentAt(Date.now());
    },
  });

  const verify = useAction(
    (_key: string, memberId?: string) =>
      memberApi.verifyCode(slug, { ...target(), code, member_id: memberId }),
    {
      onSuccess: (result) => {
        if (result.choose) setChoose(result.choose);
        else void signedInWith(result);
      },
    },
  );

  if (!gym) return null;

  return (
    <Screen topInset style={{ justifyContent: "center", flexGrow: 1 }}>
      <View style={{ alignItems: "center", gap: space(2) }}>
        <GymLogo name={gym.name} logoUrl={gym.logo_url} size={80} />
        <Title style={{ textAlign: "center", marginTop: space(2) }}>{gym.name}</Title>
        <Txt color={colors.muted}>{t("app.signIn.title")}</Txt>
      </View>

      {!sentTo ? (
        <Card style={{ gap: space(4) }}>
          <Field
            label={t("app.signIn.who")}
            help={t("app.signIn.whoHelp")}
            value={who}
            onChangeText={setWho}
            keyboardType={byEmail ? "email-address" : "phone-pad"}
            autoComplete={byEmail ? "email" : "tel"}
            textContentType={byEmail ? "emailAddress" : "telephoneNumber"}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="send"
            onSubmitEditing={() => send.run()}
            testID="who"
          />
          <ActionStatus action={send} />
          <Button
            label={t("app.signIn.sendCode")}
            busy={send.busy}
            disabled={!who.trim()}
            onPress={() => send.run()}
            testID="send-code"
          />
          <LinkButton
            label={byEmail ? t("mobile.signIn.phone") : t("mobile.signIn.email")}
            onPress={() => {
              setByEmail((value) => !value);
              setWho("");
            }}
          />
        </Card>
      ) : choose ? (
        <Card style={{ gap: space(3) }}>
          <Txt weight="semibold" accessibilityRole="header">
            {t("app.signIn.whoAreYou")}
          </Txt>
          {choose.map((person) => (
            <Button
              key={person.id}
              variant="secondary"
              label={person.name}
              busy={verify.busy}
              onPress={() => verify.run(person.id)}
            />
          ))}
          <ActionStatus action={verify} />
        </Card>
      ) : (
        <Card style={{ gap: space(4) }}>
          <Txt color={colors.muted}>{t("app.signIn.sent", { to: sentTo })}</Txt>
          <Field
            label={t("app.signIn.code")}
            value={code}
            onChangeText={(value) => {
              const digits = value.replace(/\D/g, "").slice(0, 6);
              setCode(digits);
            }}
            keyboardType="number-pad"
            // Fills the code from the SMS where the phone offers it.
            autoComplete="sms-otp"
            textContentType="oneTimeCode"
            autoFocus
            maxLength={6}
            returnKeyType="done"
            onSubmitEditing={() => code.length === 6 && verify.run(undefined)}
            testID="code"
          />
          <ActionStatus action={verify} />
          <Button
            label={t("app.signIn.submit")}
            busy={verify.busy}
            disabled={code.length !== 6}
            onPress={() => verify.run(undefined)}
            testID="sign-in"
          />
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <LinkButton
              label={t("app.signIn.again")}
              align="flex-start"
              onPress={() => {
                setSentTo(null);
                setCode("");
                setSentAt(null);
              }}
            />
            <LinkButton
              label={
                wait > 0
                  ? t("mobile.signIn.resendIn", { seconds: wait })
                  : t("mobile.signIn.resend")
              }
              color={wait > 0 ? colors.faint : undefined}
              onPress={() => {
                if (wait === 0) send.run();
              }}
            />
          </View>
        </Card>
      )}

      {gym.join_form && !sentTo ? (
        <View style={{ alignItems: "center" }}>
          <Txt color={colors.muted} size={15}>
            {t("app.join.notYet")}
          </Txt>
          <LinkButton label={t("app.join.ask")} onPress={() => router.push("/join")} />
        </View>
      ) : null}

      <LanguageSwitch />
      <LinkButton
        label={t("mobile.switchGym")}
        color={colors.faint}
        onPress={() => void closeGym()}
      />
    </Screen>
  );
}
