"use client";

import Link from "next/link";

import { Button } from "@/components/Button";
import { Row } from "@/components/ui/Card";
import { t } from "@/i18n";
import { useMember } from "@/lib/memberSession";

export default function MemberProfile() {
  const { me, slug, signOut } = useMember();
  if (!me) return null;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {me.photo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={me.photo_url}
            alt=""
            className="size-16 rounded-full object-cover"
          />
        )}
        <div>
          <h1 className="text-xl font-semibold">{me.name}</h1>
          <p className="text-sm text-slate-500">{me.member_code}</p>
        </div>
      </div>
      <dl className="rounded-2xl bg-white p-4">
        <Row label={t("member.phone")}>{me.phone}</Row>
        <Row label={t("member.email")}>{me.email ?? "—"}</Row>
      </dl>
      <p className="text-xs text-slate-500">{t("app.profile.readOnly")}</p>
      <Link
        href={`/${slug}/notices`}
        className="block text-sm text-brand-700 underline"
      >
        {t("app.notices")}
      </Link>
      <Button variant="secondary" block onClick={() => void signOut()}>
        {t("common.signOut")}
      </Button>
    </div>
  );
}
