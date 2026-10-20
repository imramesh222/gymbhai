"use client";

import { X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
import { t } from "@/i18n";
import { errorMessage, membersApi } from "@/lib/api";
import { useIdempotencyKey } from "@/lib/idempotency";

/**
 * Who else a family or couple plan covers (PLAN.md §19.1): members found by
 * name, phone or code, or added here with a name and number. The member the
 * sale is for pays for everyone.
 */
export function GroupPeople({
  seats,
  value,
  onChange,
  payerId,
  payerName,
  defaultPhone,
  branchId,
}: {
  seats: number;
  value: Picked[];
  onChange: (value: Picked[]) => void;
  payerId?: string;
  payerName?: string;
  /** A child often shares a parent's number. */
  defaultPhone?: string;
  branchId?: string;
}) {
  const room = seats - 1 - value.length;
  const [adding, setAdding] = useState(false);
  return (
    <div className="space-y-3 rounded-lg bg-slate-50 p-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-800">{t("sale.withWho")}</h3>
        <p className="text-xs text-slate-600">
          {payerName
            ? t("sale.withHelp", { count: seats, name: payerName })
            : t("sale.withHelpNew", { count: seats })}
        </p>
      </div>
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((person) => (
            <li
              key={person.id}
              className="inline-flex items-center gap-1 rounded-full bg-white py-1 pr-1 pl-3 text-sm font-medium text-slate-800 ring-1 ring-hairline"
            >
              {person.name}
              {person.first && (
                <span className="text-xs font-normal text-slate-500">
                  · {t("sale.withFirst")}
                </span>
              )}
              <button
                type="button"
                onClick={() => onChange(value.filter((p) => p.id !== person.id))}
                className="rounded-full p-1 hover:bg-slate-100"
                aria-label={t("picker.clear", { name: person.name })}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {room > 0 ? (
        <>
          <MemberPicker
            label={t("sale.withFind")}
            value={null}
            onChange={(picked) => picked && onChange([...value, picked])}
            exclude={[...(payerId ? [payerId] : []), ...value.map((p) => p.id)]}
          />
          <p className="text-xs text-slate-500">
            {t("sale.withPlaces", { count: room })}
          </p>
          {adding ? (
            <NewPerson
              defaultPhone={defaultPhone ?? ""}
              branchId={branchId}
              onAdded={(person) => {
                onChange([...value, person]);
                setAdding(false);
              }}
            />
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
              {t("sale.withNew")}
            </Button>
          )}
        </>
      ) : (
        <p className="text-xs text-slate-500">{t("sale.withFull")}</p>
      )}
    </div>
  );
}

function NewPerson({
  defaultPhone,
  branchId,
  onAdded,
}: {
  defaultPhone: string;
  branchId?: string;
  onAdded: (person: Picked) => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState(defaultPhone);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const saving = useIdempotencyKey();

  async function add() {
    if (!name.trim() || !phone.trim()) return;
    setPending(true);
    setError(null);
    try {
      const body = { name: name.trim(), phone, home_branch_id: branchId || null };
      const created = await membersApi.create(body, saving.keyFor(body));
      saving.succeeded();
      onAdded({ id: created.member.id, name: created.member.name, first: true });
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  // Not a <form>: it sits inside the sale's own form.
  return (
    <div className="space-y-2 rounded-lg bg-white p-3 ring-1 ring-hairline">
      <div className="grid gap-2 sm:grid-cols-2">
        {/* Not required: the sale's own form mustn't wait on them. */}
        <Field label={t("sale.withNewName")} value={name} onChange={setName} />
        <Field
          label={t("sale.withNewPhone")}
          value={phone}
          onChange={setPhone}
          type="tel"
          inputMode="tel"
          help={t("sale.withNewPhoneHelp")}
        />
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <Button size="sm" onClick={() => void add()} disabled={pending}>
        {pending ? t("common.saving") : t("sale.withNewAdd")}
      </Button>
    </div>
  );
}
