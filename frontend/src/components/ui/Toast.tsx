"use client";

import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { t } from "@/i18n";

type Tone = "success" | "error" | "info";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  tone: Tone;
  text: string;
  action?: ToastAction;
}

type Push = (toast: Omit<ToastItem, "id">) => void;

const ToastContext = createContext<Push | null>(null);

const ICONS = { success: CircleCheck, error: CircleAlert, info: Info } as const;
const ICON_TONES = {
  success: "text-emerald-400",
  error: "text-red-400",
  info: "text-brand-300",
} as const;
// Long enough to read, longer when there is something to tap (Undo).
const SHOWN_MS = 5000;
const SHOWN_WITH_ACTION_MS = 8000;

function ToastView({
  toast,
  remove,
}: {
  toast: ToastItem;
  remove: (id: number) => void;
}) {
  const Icon = ICONS[toast.tone];
  const onDone = () => remove(toast.id);
  useEffect(() => {
    const timer = setTimeout(
      () => remove(toast.id),
      toast.action ? SHOWN_WITH_ACTION_MS : SHOWN_MS,
    );
    return () => clearTimeout(timer);
  }, [remove, toast.id, toast.action]);
  return (
    <div
      role={toast.tone === "error" ? "alert" : "status"}
      className="pointer-events-auto flex w-full items-start gap-3 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-lifted ring-1 ring-white/10"
    >
      <Icon
        className={`mt-0.5 size-4 shrink-0 ${ICON_TONES[toast.tone]}`}
        aria-hidden
      />
      <p className="min-w-0 flex-1">{toast.text}</p>
      {toast.action && (
        <button
          type="button"
          onClick={() => {
            toast.action?.onClick();
            onDone();
          }}
          className="shrink-0 font-semibold text-brand-300 hover:text-brand-200"
        >
          {toast.action.label}
        </button>
      )}
      <button
        type="button"
        onClick={onDone}
        aria-label={t("common.close")}
        className="-m-1 shrink-0 rounded p-1 text-slate-400 hover:text-white"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}

/**
 * Short confirmations after an action ("Payment recorded — receipt #42"),
 * stacked at the bottom of the screen, above the phone's tab bar.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const push = useCallback<Push>((toast) => {
    const id = next.current++;
    // Three at most: an older one makes way.
    setToasts((list) => [...list.slice(-2), { ...toast, id }]);
  }, []);
  const remove = useCallback(
    (id: number) => setToasts((list) => list.filter((toast) => toast.id !== id)),
    [],
  );
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-20 z-50 mx-auto flex w-[min(28rem,calc(100vw-2rem))] flex-col gap-2 lg:bottom-6 print:hidden"
      >
        {toasts.map((toast) => (
          <ToastView key={toast.id} toast={toast} remove={remove} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  return useMemo(() => {
    // Outside a provider (a test, a page without one): quietly nothing.
    const send = push ?? (() => undefined);
    return {
      success: (text: string, action?: ToastAction) =>
        send({ tone: "success", text, action }),
      error: (text: string) => send({ tone: "error", text }),
      info: (text: string, action?: ToastAction) =>
        send({ tone: "info", text, action }),
    };
  }, [push]);
}
