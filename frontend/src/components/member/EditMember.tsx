"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, Select, TextArea } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage, membersApi, type Branch, type MemberDetail } from "@/lib/api";
import { useGymCalendar } from "@/lib/gym";

export function EditMember({
  member,
  branches,
  open,
  onClose,
  onSaved,
}: {
  member: MemberDetail;
  branches: Branch[];
  open: boolean;
  onClose: () => void;
  onSaved: (member: MemberDetail) => void;
}) {
  const { display } = useGymCalendar();
  const [form, setForm] = useState({
    name: member.name,
    phone: member.phone,
    email: member.email ?? "",
    gender: member.gender ?? "",
    date_of_birth: member.date_of_birth ?? "",
    address: member.address ?? "",
    emergency_contact: member.emergency_contact ?? "",
    notes: member.notes ?? "",
    home_branch_id: member.home_branch_id,
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const set = (key: keyof typeof form) => (value: string) =>
    setForm({ ...form, [key]: value });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      onSaved(
        await membersApi.update(member.id, {
          ...form,
          email: form.email || null,
          gender: (form.gender || null) as MemberDetail["gender"],
          date_of_birth: form.date_of_birth || null,
          address: form.address || null,
          emergency_contact: form.emergency_contact || null,
          notes: form.notes || null,
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("member.edit")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <Field
          label={t("member.name")}
          value={form.name}
          onChange={set("name")}
          required
        />
        <Field
          label={t("member.phone")}
          value={form.phone}
          onChange={set("phone")}
          type="tel"
          required
        />
        <Field
          label={t("member.email")}
          value={form.email}
          onChange={set("email")}
          type="email"
        />
        <Select
          label={t("member.gender")}
          value={form.gender as "" | "male" | "female" | "other"}
          onChange={set("gender")}
          options={[
            { value: "female", label: t("member.gender.female") },
            { value: "male", label: t("member.gender.male") },
            { value: "other", label: t("member.gender.other") },
          ]}
        />
        <DateInput
          label={t("member.dateOfBirth")}
          value={form.date_of_birth}
          onChange={set("date_of_birth")}
          display={display}
        />
        <Field
          label={t("member.address")}
          value={form.address}
          onChange={set("address")}
        />
        <Field
          label={t("member.emergencyContact")}
          value={form.emergency_contact}
          onChange={set("emergency_contact")}
        />
        {branches.length > 1 && (
          <Select
            label={t("member.homeBranch")}
            value={form.home_branch_id}
            onChange={set("home_branch_id")}
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        )}
        <TextArea
          label={t("member.notes")}
          value={form.notes}
          onChange={set("notes")}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {pending ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
