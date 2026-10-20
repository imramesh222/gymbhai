"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { doorApi, errorMessage, type Branch, type ReaderKind } from "@/lib/api";

/**
 * Settings → Door scanners → Add a fingerprint or face reader (PLAN.md §18.2):
 * the brand, chosen for each reader, its branch and serial number; then how
 * to point the reader (ZKTeco) or the bridge (Hikvision) at GymBhai.
 */
export function AddReader({
  branches,
  onClose,
  onAdded,
}: {
  branches: Branch[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [kind, setKind] = useState<ReaderKind>("zkteco");
  const [name, setName] = useState("");
  const [branchId, setBranchId] = useState("");
  const [serial, setSerial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [added, setAdded] = useState<{ kind: ReaderKind; token: string } | null>(null);
  // The branches may still be loading when the dialog opens.
  const branch = branchId || branches[0]?.id || "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const made = await doorApi.addReader({
        kind,
        name,
        branch_id: branch,
        serial: serial.trim() || null,
      });
      setAdded({ kind, token: made.token });
      onAdded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("readers.add")}>
      {added ? (
        <Setup kind={added.kind} token={added.token} onClose={onClose} />
      ) : (
        <form onSubmit={(e) => void submit(e)} className="space-y-3">
          <Select<ReaderKind>
            label={t("readers.brand")}
            value={kind}
            onChange={setKind}
            options={[
              { value: "zkteco", label: t("readers.kind.zkteco") },
              { value: "hikvision", label: t("readers.kind.hikvision") },
            ]}
          />
          <Field
            label={t("readers.name")}
            value={name}
            onChange={setName}
            required
            help={t("readers.nameHelp")}
          />
          {branches.length > 1 && (
            <Select
              label={t("sale.branch")}
              value={branch}
              onChange={setBranchId}
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
            />
          )}
          <Field
            label={t("readers.serial")}
            value={serial}
            onChange={setSerial}
            required={kind === "zkteco"}
            optional={kind !== "zkteco"}
            optionalLabel={t("common.optional")}
            help={t("readers.serialHelp")}
          />
          <p className="text-xs text-slate-500">{t("readers.unconfirmed")}</p>
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" block disabled={pending || !branch}>
            {pending ? t("common.saving") : t("readers.add")}
          </Button>
        </form>
      )}
    </Dialog>
  );
}

/** How to point the reader at GymBhai, once it's added. */
function Setup({
  kind,
  token,
  onClose,
}: {
  kind: ReaderKind;
  token: string;
  onClose: () => void;
}) {
  const host = typeof window === "undefined" ? "" : window.location.host;
  const bridge = JSON.stringify(
    {
      server: `https://${host}`,
      interval: 5,
      readers: [
        {
          token,
          address: "http://192.168.1.64",
          username: "admin",
          password: "…",
        },
      ],
    },
    null,
    2,
  );
  return (
    <div className="space-y-3 text-sm text-slate-700">
      <Notice tone="success">{t("readers.added")}</Notice>
      {kind === "zkteco" ? (
        <ol className="list-decimal space-y-1 pl-5">
          <li>{t("readers.zk.step1")}</li>
          <li>{t("readers.zk.step2", { host })}</li>
          <li>{t("readers.zk.step3")}</li>
          <li>{t("readers.zk.step4")}</li>
        </ol>
      ) : (
        <>
          <ol className="list-decimal space-y-1 pl-5">
            <li>{t("readers.hik.step1")}</li>
            <li>{t("readers.hik.step2")}</li>
            <li>{t("readers.hik.step3")}</li>
          </ol>
          <pre
            className="max-h-56 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100"
            aria-label={t("readers.hik.config")}
          >
            {bridge}
          </pre>
          <p className="text-xs text-amber-800">{t("readers.hik.once")}</p>
        </>
      )}
      <Button block variant="secondary" onClick={onClose}>
        {t("common.close")}
      </Button>
    </div>
  );
}
