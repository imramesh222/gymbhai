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
import type { Roster } from "@shared/door/offline";
import {
  decide,
  forgetEverything,
  keepRoster,
  markSent,
  storedRoster,
  tooOld,
  waiting,
  type StoredRoster,
} from "@/lib/kioskOffline";
import type { PublicGym } from "@/lib/memberApi";
import { useLoad } from "@/lib/useLoad";

const TOKEN_KEY = "gymbhai.kiosk";
const SHOW_FOR_MS = 3000;
// Online, the roster is fetched again this often; scans waiting to be sent
// are tried every half minute (PLAN.md §19.2).
const ROSTER_EVERY_MS = 5 * 60 * 1000;
const RETRY_EVERY_MS = 30 * 1000;
// A scan the server hasn't answered by then is decided here.
const ONLINE_WAIT_MS = 4000;

/** No answer from the server: no signal, a timeout, or the server down. */
function unreachable(err: unknown): boolean {
  return !(err instanceof ApiError) || err.status === 0 || err.status >= 500;
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

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
  const { me, loading, can, signOut } = useAuth();
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
    // Signed in, but not as someone who can set up this gym's door: say why.
    const why = !me
      ? t("kiosk.needSignIn")
      : me.staff.is_platform_admin
        ? t("kiosk.adminHasNoGym")
        : t("kiosk.noPermission");
    return (
      <main className="mx-auto max-w-md p-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight">{t("kiosk.title")}</h1>
        <p className="mt-2 text-slate-600">{why}</p>
        {me ? (
          <button
            type="button"
            onClick={() => void signOut()}
            className="mt-6 inline-block font-semibold text-brand-700 underline"
          >
            {t("kiosk.signInAsOwner")}
          </button>
        ) : (
          <Link
            href="/staff/login?next=/kiosk"
            className="mt-6 inline-block font-semibold text-brand-700 underline"
          >
            {t("home.signIn")}
          </Link>
        )}
      </main>
    );
  }
  const list = branches.data ?? [];
  const chosen = branchId || list[0]?.id || "";
  return (
    <main className="mx-auto max-w-md p-6 sm:p-8">
      <h1 className="text-2xl font-bold tracking-tight">{t("kiosk.title")}</h1>
      <p className="mt-2 text-slate-600">{t("kiosk.registerHelp")}</p>
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
        className="mt-6 space-y-4 rounded-2xl bg-surface p-5 shadow-card ring-1 ring-hairline"
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
        <Button type="submit" size="lg" block disabled={!chosen}>
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
  // What it lets people in by with no internet (PLAN.md §19.2).
  const [stored, setStored] = useState<StoredRoster | null>(() => storedRoster());
  const [unsent, setUnsent] = useState(() => waiting().length);
  const hide = useRef<ReturnType<typeof setTimeout> | null>(null);

  const revoked = useCallback(() => {
    forgetEverything();
    onRevoked();
  }, [onRevoked]);

  /** Scans waiting go first; only then a new roster, so its visit counts
   * include them. */
  const sync = useCallback(async () => {
    try {
      const scans = waiting();
      if (scans.length) {
        await client.request("/api/v1/kiosk/scans", {
          method: "POST",
          body: JSON.stringify({ scans }),
        });
        markSent(scans.map((s) => s.client_id));
        setUnsent(waiting().length);
      }
      const roster = await client.request<Roster>("/api/v1/kiosk/roster");
      setStored(keepRoster(roster));
      setOnline(true);
      // Photos into the kiosk's service worker, for the cards offline.
      for (const m of roster.members)
        if (m.photo_url) void fetch(m.photo_url).catch(() => undefined);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return revoked();
      if (unreachable(err)) setOnline(false);
    }
  }, [client, revoked]);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/kiosk-sw.js", { scope: "/kiosk" })
        .catch(() => undefined);
    }
    client
      .request<{ branch_name: string; gym: PublicGym }>("/api/v1/kiosk/me")
      .then(setInfo)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) revoked();
      });
    // Once the page is up: it talks to the server and to storage.
    void Promise.resolve().then(sync);
    const roster = setInterval(() => void sync(), ROSTER_EVERY_MS);
    const retry = setInterval(() => {
      if (waiting().length) void sync();
    }, RETRY_EVERY_MS);
    const clock = setInterval(() => setNow(new Date()), 10_000);
    const status = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) void sync();
    };
    window.addEventListener("online", status);
    window.addEventListener("offline", status);
    return () => {
      clearInterval(roster);
      clearInterval(retry);
      clearInterval(clock);
      window.removeEventListener("online", status);
      window.removeEventListener("offline", status);
    };
  }, [client, revoked, sync]);

  const show = useCallback((scanned: ScanResult) => {
    setResult(scanned);
    if (hide.current) clearTimeout(hide.current);
    hide.current = setTimeout(() => setResult(null), SHOW_FOR_MS);
  }, []);

  const onCode = useCallback(
    async (code: string) => {
      try {
        const scanned = await withTimeout(
          client.request<ScanResult>("/api/v1/kiosk/scan", {
            method: "POST",
            body: JSON.stringify({ code }),
          }),
          ONLINE_WAIT_MS,
        );
        setOnline(true);
        show(scanned);
        return;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return revoked();
        if (!unreachable(err)) return;
        setOnline(false);
      }
      // No internet: from the roster, if there is one.
      const kept = storedRoster();
      if (!kept) return;
      const offline = decide(code, kept);
      setUnsent(waiting().length);
      show(offline.result);
    },
    [client, revoked, show],
  );

  const display = info?.gym.date_display ?? "ad";
  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center gap-6 bg-slate-950 p-6 text-white">
      {/* A glow behind the clock so a dark screen across the room still reads
          as switched on. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(50%_45%_at_50%_35%,rgba(29,95,209,0.35),transparent)]"
      />
      {!online && <OfflineBanner stored={stored} unsent={unsent} />}
      {result ? (
        <div className="relative w-full max-w-lg">
          <ScanCard result={result} display={display} />
        </div>
      ) : (
        <div className="relative text-center">
          {info?.gym.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={info.gym.logo_url}
              alt=""
              className="mx-auto mb-5 size-24 rounded-2xl bg-white object-contain p-2 ring-1 ring-white/20"
            />
          )}
          <p className="text-3xl font-bold tracking-tight">{info?.gym.name}</p>
          <p className="mt-1 text-slate-400">{info?.branch_name}</p>
          <p className="mt-6 text-7xl font-light tracking-tight tabular-nums">
            {now.toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "Asia/Kathmandu",
            })}
          </p>
          <p className="mt-6 text-xl text-slate-300">{t("kiosk.showQr")}</p>
        </div>
      )}
      <div
        className={`relative w-full max-w-xs overflow-hidden rounded-2xl ring-1 ring-white/15 ${result ? "hidden" : ""}`}
      >
        <Scanner onCode={(code) => void onCode(code)} paused={Boolean(result)} />
      </div>
    </main>
  );
}

function OfflineBanner({
  stored,
  unsent,
}: {
  stored: StoredRoster | null;
  unsent: number;
}) {
  // With a fresh enough roster the door keeps working: amber, not red.
  const working = stored !== null && !tooOld(stored);
  const saved = stored
    ? new Date(stored.roster.server_time).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kathmandu",
      })
    : "";
  return (
    <div
      className={`relative w-full max-w-lg rounded-2xl p-3 text-center font-semibold shadow-lifted ${
        working ? "bg-amber-500 text-slate-950" : "bg-red-600"
      }`}
    >
      <p>
        {working
          ? t("kiosk.offlineList", { time: saved })
          : stored
            ? t("kiosk.offlineTooLong")
            : t("kiosk.offline")}
      </p>
      {unsent > 0 && (
        <p className="mt-1 text-sm font-medium">
          {t("kiosk.offlineWaiting", { count: unsent })}
        </p>
      )}
    </div>
  );
}
