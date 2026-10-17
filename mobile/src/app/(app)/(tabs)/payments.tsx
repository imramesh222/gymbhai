/**
 * Payments (PLAN.md §17.5): what they owe, what they sent from the app, and
 * every payment with its receipt, shared as a PDF through the share sheet.
 */
import { View } from "react-native";

import { formatDateTime } from "@shared/dates";
import { t, type MessageKey } from "@shared/i18n";
import type { Payment } from "@shared/types";

import { Icon } from "@/components/Icon";
import { Money, Screen } from "@/components/Screen";
import {
  ActionStatus,
  Card,
  Label,
  LinkButton,
  Spinner,
  Title,
  Txt,
} from "@/components/ui";
import { useBrand } from "@/components/brand";
import { useMe, usePayments } from "@/lib/hooks";
import { shareReceipt } from "@/lib/images";
import { memberApi } from "@/lib/memberApi";
import { colors, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

function ReceiptButton({ payment }: { payment: Payment }) {
  const brand = useBrand();
  const share = useAction(async () =>
    shareReceipt(await memberApi.receiptLink(payment.id)),
  );
  return (
    <View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space(1) }}>
        <Icon name="share" size={16} color={brand} />
        <LinkButton
          align="flex-start"
          label={
            share.busy
              ? t("common.loading")
              : t("app.payments.receiptFor", { number: payment.receipt_no })
          }
          onPress={() => share.run()}
        />
      </View>
      <ActionStatus action={share} />
    </View>
  );
}

export default function Payments() {
  const me = useMe().data;
  const payments = usePayments();
  if (!me || !payments.data) return <Spinner />;
  const display = me.gym.date_display;
  const { dues, requests } = payments.data;

  return (
    <Screen onRefresh={() => payments.refetch()}>
      <Title>{t("app.tab.payments")}</Title>
      {dues > 0 ? (
        <Card
          style={{
            backgroundColor: colors.amberBg,
            borderColor: "#fde68a",
            flexDirection: "row",
            gap: space(2),
          }}
        >
          <Txt color={colors.amberInk}>{t("app.home.owes")}</Txt>
          <Money paisa={dues} weight="semibold" color={colors.amberInk} />
        </Card>
      ) : null}

      {requests.length > 0 ? (
        <View style={{ gap: space(2) }}>
          <Label>{t("app.payments.requests")}</Label>
          {requests.map((r) => (
            <Card key={r.id} style={{ gap: space(1) }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Txt>{r.plan_name}</Txt>
                <Money paisa={r.amount} />
              </View>
              <Txt
                size={13}
                color={r.status === "rejected" ? colors.red : colors.faint}
              >
                {t(`app.request.${r.status}` as MessageKey)}
                {r.reject_reason ? ` — ${r.reject_reason}` : ""}
              </Txt>
            </Card>
          ))}
        </View>
      ) : null}

      <View style={{ gap: space(2) }}>
        <Label>{t("app.payments.paid")}</Label>
        {payments.data.payments.length === 0 ? (
          <Txt color={colors.faint}>{t("payment.none")}</Txt>
        ) : null}
        {payments.data.payments.map((p) => (
          <Card key={p.id} style={{ flexDirection: "row", gap: space(3) }}>
            <View style={{ flex: 1 }}>
              <Txt weight="medium">
                {p.kind === "refund"
                  ? t("payment.refund")
                  : t(`method.${p.method}` as MessageKey)}
              </Txt>
              <Txt size={13} color={colors.faint}>
                #{p.receipt_no} · {formatDateTime(p.paid_at, display)}
              </Txt>
              <ReceiptButton payment={p} />
            </View>
            <Money
              paisa={p.kind === "refund" ? -p.amount : p.amount}
              weight="semibold"
            />
          </Card>
        ))}
      </View>
    </Screen>
  );
}
