"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Scanner } from "@/components/Scanner";
import { ScanCard } from "@/components/door/ScanCard";
import { PageHeader } from "@/components/ui/Card";
import { Select, TextArea } from "@/components/ui/inputs";
import { t } from "@/i18n";
import {
  branchesApi,
  doorApi,
  errorMessage,
  membersApi,
  type Member,
  type ScanResult,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/**
 * Check-in from the staff phone or desk (§4.3): scan with the camera, or find
 * the member by name for a dead phone or a forgotten card.
 */
export default function DoorPage() {
  const { can } = useAuth();
  const { display } = useGymCalendar();
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  const [branchId, setBranchId] = useState("");
  const [camera, setCamera] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [search, setSearch] = useState("");
  const [found, setFound] = useState<Member[]>([]);
  const [overrideNote, setOverrideNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const branch = branchId || branches[0]?.id || "";

  async function run(action: () => Promise<ScanResult>) {
    setError(null);
    try {
      setResult(await action());
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function find(q: string) {
    setSearch(q);
    if (q.trim().length < 2) return setFound([]);
    const list = await membersApi.list({ q, limit: 8 }).catch(() => null);
    setFound(list?.items ?? []);
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("door.title")} />
      {branches.length > 1 && (
        <Select
          label={t("sale.branch")}
          value={branch}
          onChange={setBranchId}
          options={branches.map((b) => ({ value: b.id, label: b.name }))}
        />
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {result && (
        <div className="space-y-2">
          <ScanCard result={result} display={display} />
          {result.can_override && result.member_id && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run(() =>
                  doorApi.manual({
                    member_id: result.member_id!,
                    branch_id: branch,
                    override: true,
                    note: overrideNote,
                  }),
                );
              }}
              className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 p-3"
            >
              <TextArea
                label={t("door.overrideReason")}
                value={overrideNote}
                onChange={setOverrideNote}
                required
              />
              <Button type="submit" variant="secondary">
                {t("door.letInAnyway")}
              </Button>
            </form>
          )}
          <Button variant="ghost" onClick={() => setResult(null)}>
            {t("door.next")}
          </Button>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <Button variant="secondary" onClick={() => setCamera(!camera)}>
            {camera ? t("door.cameraOff") : t("door.cameraOn")}
          </Button>
          <div className="mt-3 max-w-xs">
            <Scanner
              camera={camera}
              paused={Boolean(result)}
              onCode={(code) => void run(() => doorApi.scan(code, branch))}
            />
          </div>
          <p className="mt-2 text-xs text-slate-500">{t("door.usbHelp")}</p>
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="door-search">
            {t("door.findMember")}
          </label>
          <input
            id="door-search"
            value={search}
            onChange={(e) => void find(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5"
          />
          <ul className="mt-2 divide-y divide-slate-100 rounded-lg bg-white">
            {found.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <span>
                  {m.name} <span className="text-slate-500">· {m.member_code}</span>
                </span>
                {can("door.check_in") && (
                  <Button
                    variant="secondary"
                    onClick={() =>
                      run(() => doorApi.manual({ member_id: m.id, branch_id: branch }))
                    }
                  >
                    {t("door.checkIn")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
