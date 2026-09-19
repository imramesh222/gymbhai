"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Scanner } from "@/components/Scanner";
import { ScanCard } from "@/components/door/ScanCard";
import { Select } from "@/components/ui/inputs";
import { t } from "@/i18n";
import {
  ApiError,
  branchesApi,
  createClient,
  doorApi,
  errorMessage,
  type ScanResult,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PublicGym } from "@/lib/memberApi";
import { useLoad } from "@/lib/useLoad";

const TOKEN_KEY = "gymbahi.kiosk";
const SHOW_FOR_MS = 3000;

function storedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

// The device token lives in this browser's storage. Read through
// useSyncExternalStore so the server render ("not known yet") and the first
// client render agree.
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
function saveToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Private browsing: the kiosk will need registering again after a reload.
  }
  listeners.forEach((listener) => listener());
}

/**
 * The door scanner (PLAN.md §4.3). A tablet or old phone at the entrance,
 * registered to one branch. It can check people in and nothing else.
 */
export default function KioskPage() {
  const token = useSyncExternalStore(subscribe, storedToken, () => undefined);
  if (token === undefined) return null;
  return token ? (
    <Door token={token} onRevoked={() => saveToken(null)} />
  ) : (
    <Register onRegistered={saveToken} />
  );
}

function Register({ onRegistered }: { onRegistered: (token: string) => void }) {
  const { me, loading, can } = useAuth();
  const branches = useLoad(
    () => (me ? branchesApi.list() : Promise.resolve([])),
    [me?.staff.id],
  );
  const [branchId, setBranchId] = useState("");
  const [name, setName] = useState(t("kiosk.defaultName"));
  const [error, setError] = useState<string | null>(null);

  if (loading)
    return <p className="p-10 text-center text-slate-500">{t("common.loading")}</p>;
  if (!me || !can("setup.devices")) {
    return (
      <main className="mx-auto max-w-md p-8 text-center">
        <h1 className="text-2xl font-bold">{t("kiosk.title")}</h1>
        <p className="mt-2 text-slate-600">{t("kiosk.needSignIn")}</p>
        <Link
          href="/staff/login"
          className="mt-6 inline-block font-semibold text-brand-700 underline"
        >
          {t("home.signIn")}
        </Link>
      </main>
    );
  }
  const list = branches.data ?? [];
  const chosen = branchId || list[0]?.id || "";
  return (
    <main className="mx-auto max-w-md space-y-4 p-8">
      <h1 className="text-2xl font-bold">{t("kiosk.title")}</h1>
      <p className="text-slate-600">{t("kiosk.registerHelp")}</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const { token } = await doorApi.registerDevice(chosen, name);
            onRegistered(token);
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
        className="space-y-3"
      >
        <Select
          label={t("sale.branch")}
          value={chosen}
          onChange={setBranchId}
          options={list.map((b) => ({ value: b.id, label: b.name }))}
        />
        <Field label={t("kiosk.name")} value={name} onChange={setName} required />
        {error && <Notice tone="error">{error}</Notice>}
        {/* Not before the branches have loaded: an empty branch would be refused. */}
        <Button type="submit" block disabled={!chosen}>
          {t("kiosk.use", { branch: list.find((b) => b.id === chosen)?.name ?? "" })}
        </Button>
      </form>
    </main>
  );
}

function Door({ token, onRevoked }: { token: string; onRevoked: () => void }) {
  const client = useMemo(
    () => createClient({ headers: () => ({ "X-Device-Token": token }) }),
    [token],
  );
  const [info, setInfo] = useState<{ branch_name: string; gym: PublicGym } | null>(
    null,
  );
  const [result, setResult] = useState<ScanResult | null>(null);
  const [online, setOnline] = useState(true);
  const [now, setNow] = useState(() => new Date());
  const hide = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    client
      .request<{ branch_name: string; gym: PublicGym }>("/api/v1/kiosk/me")
      .then(setInfo)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) onRevoked();
      });
    const clock = setInterval(() => setNow(new Date()), 10_000);
    const status = () => setOnline(navigator.onLine);
    window.addEventListener("online", status);
    window.addEventListener("offline", status);
    return () => {
      clearInterval(clock);
      window.removeEventListener("online", status);
      window.removeEventListener("offline", status);
    };
  }, [client, onRevoked]);

  const onCode = useCallback(
    async (code: string) => {
      try {
        const scanned = await client.request<ScanResult>("/api/v1/kiosk/scan", {
          method: "POST",
          body: JSON.stringify({ code }),
        });
        setOnline(true);
        setResult(scanned);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return onRevoked();
        setOnline(false);
        return;
      }
      if (hide.current) clearTimeout(hide.current);
      hide.current = setTimeout(() => setResult(null), SHOW_FOR_MS);
    },
    [client, onRevoked],
  );

  const display = info?.gym.date_display ?? "ad";
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-slate-900 p-6 text-white">
      {!online && (
        <p className="w-full max-w-lg rounded-xl bg-red-600 p-3 text-center font-semibold">
          {t("kiosk.offline")}
        </p>
      )}
      {result ? (
        <div className="w-full max-w-lg">
          <ScanCard result={result} display={display} />
        </div>
      ) : (
        <div className="text-center">
          {info?.gym.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={info.gym.logo_url}
              alt=""
              className="mx-auto mb-4 size-24 rounded-xl bg-white object-contain"
            />
          )}
          <p className="text-3xl font-bold">{info?.gym.name}</p>
          <p className="text-slate-300">{info?.branch_name}</p>
          <p className="mt-4 text-6xl font-light tabular-nums">
            {now.toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "Asia/Kathmandu",
            })}
          </p>
          <p className="mt-4 text-xl">{t("kiosk.showQr")}</p>
        </div>
      )}
      <div className={`w-full max-w-xs ${result ? "hidden" : ""}`}>
        <Scanner onCode={(code) => void onCode(code)} paused={Boolean(result)} />
      </div>
    </main>
  );
}
