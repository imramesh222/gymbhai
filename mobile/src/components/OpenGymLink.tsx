/**
 * A link into the app (PLAN.md §17.5): gymbhai://<gym>[/<screen>] from the
 * welcome SMS, https://app.gymbhai.com/<gym>/... once app links are
 * published, or a notification about another gym. Opens that gym, then the
 * screen the link was for.
 */
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";

import { t } from "@shared/i18n";

import { Button, Notice, Spinner } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { memberApi } from "@/lib/memberApi";
import { useSession } from "@/lib/session";
import { space } from "@/lib/theme";

const SCREENS = new Set(["renew", "payments", "visits", "notices", "freeze", "join"]);

export function OpenGymLink() {
  const params = useLocalSearchParams<{ gym: string; rest?: string | string[] }>();
  const { gym, openGym } = useSession();
  const [problem, setProblem] = useState<string | null>(null);
  const slug = String(params.gym ?? "").toLowerCase();
  const rest = Array.isArray(params.rest)
    ? params.rest
    : params.rest
      ? [params.rest]
      : [];

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (gym?.slug !== slug) await openGym(await memberApi.gym(slug));
        if (cancelled) return;
        const screen = rest[0] && SCREENS.has(rest[0]) ? `/${rest[0]}` : "/";
        router.replace(screen as never);
      } catch (error) {
        if (!cancelled) setProblem(errorMessage(error));
      }
    })();
    return () => {
      cancelled = true;
    };
    // Once per link.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  return (
    <View
      style={{ flex: 1, justifyContent: "center", padding: space(6), gap: space(4) }}
    >
      {problem ? (
        <>
          <Notice tone="error">{problem}</Notice>
          <Button
            label={t("common.back")}
            onPress={() => router.replace("/" as never)}
          />
        </>
      ) : (
        <Spinner />
      )}
    </View>
  );
}
