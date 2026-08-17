"use client";

/**
 * App-wide notification cards, bottom-right — the replacement for dumping
 * raw error text into the middle of a page. Call `useToast()` from any
 * Client Component: `toast.error("...")`, `toast.success("...")`,
 * `toast.info("...")`. Every message shown through this must already be
 * plain, human language — this component doesn't sanitize what it's given
 * (see `describeError` in lib/api-error.ts for the one place that turns a
 * raw failure into a safe sentence before it ever reaches here).
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: string;
  variant: ToastVariant;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

// Errors stay up longer than a success confirmation — someone reading a
// failure needs more than a couple seconds to actually register what
// happened, while a success toast is just a quick confirmation of
// something they already saw happen on screen.
const DURATION_MS: Record<ToastVariant, number> = {
  success: 4000,
  info: 4000,
  error: 7000,
};

const VARIANT_META: Record<
  ToastVariant,
  { icon: typeof CheckCircle2; className: string; iconClassName: string }
> = {
  success: {
    icon: CheckCircle2,
    className: "border-primary/30 bg-card",
    iconClassName: "text-primary",
  },
  error: {
    icon: AlertCircle,
    className: "border-destructive/30 bg-card",
    iconClassName: "text-destructive",
  },
  info: {
    icon: Info,
    className: "border-border bg-card",
    iconClassName: "text-muted-foreground",
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (variant: ToastVariant, message: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((current) => [...current, { id, variant, message }]);
      const timer = setTimeout(() => dismiss(id), DURATION_MS[variant]);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (message: string) => show("success", message),
      error: (message: string) => show("error", message),
      info: (message: string) => show("info", message),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const meta = VARIANT_META[toast.variant];
  const Icon = meta.icon;
  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      className={`animate-in slide-in-from-bottom-2 fade-in pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg ${meta.className}`}
    >
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${meta.iconClassName}`} />
      <p className="flex-1 text-sm text-foreground">{toast.message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="shrink-0 rounded-md p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** Throws if called outside `ToastProvider` — every page renders under the
 * root layout's provider, so this should never actually happen; failing
 * loudly beats a silently-dropped notification. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
