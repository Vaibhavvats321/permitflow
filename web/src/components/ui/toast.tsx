"use client";

import { AlertCircle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api";

/**
 * Toasts.
 *
 * Written rather than installed because the whole thing is about 100 lines and
 * the alternatives are either a dependency or a notification API that would only
 * ever be used this way.
 *
 * Toasts here confirm an action that the user already sees the result of, and
 * never carry the only copy of important information. If the outcome is worth
 * reading carefully it belongs in the page, not in something that disappears.
 */

export type ToastTone = "success" | "error" | "info" | "warning";

interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
  /** Optional single action, for "View application" after a submit. */
  action?: { label: string; onClick: () => void };
}

interface ToastApi {
  push: (toast: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const TONE_PRESENTATION: Record<
  ToastTone,
  { icon: typeof Info; className: string; iconClassName: string }
> = {
  success: {
    icon: CheckCircle2,
    className: "border-positive/25 bg-positive-soft",
    iconClassName: "text-positive",
  },
  error: {
    icon: XCircle,
    className: "border-critical/25 bg-critical-soft",
    iconClassName: "text-critical",
  },
  warning: {
    icon: AlertCircle,
    className: "border-attention/25 bg-attention-soft",
    iconClassName: "text-attention",
  },
  info: {
    icon: Info,
    className: "border-line bg-surface",
    iconClassName: "text-brand-600",
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { ...toast, id }]);
      // Errors stay longer: they usually carry text the user has to read.
      const duration = toast.tone === "error" ? 7000 : 4500;
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), duration),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      push,
      dismiss,
      success: (title, description) => push({ tone: "success", title, description }),
      error: (title, description) => push({ tone: "error", title, description }),
      info: (title, description) => push({ tone: "info", title, description }),
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/*
        `aria-live="polite"` so a confirmation is announced when it appears
        rather than interrupting whatever the user is doing. `role="status"` is
        the pairing for that level.
      */}
      <div
        aria-live="polite"
        role="status"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:top-0 sm:items-end sm:p-6"
      >
        {toasts.map((toast) => {
          const presentation = TONE_PRESENTATION[toast.tone];
          const Icon = presentation.icon;
          return (
            <div
              key={toast.id}
              className={cn(
                "animate-slide-up pointer-events-auto flex w-full max-w-sm items-start gap-3",
                "rounded-panel border px-4 py-3 shadow-floating",
                presentation.className,
              )}
            >
              <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", presentation.iconClassName)} />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-ink-900">{toast.title}</p>
                {toast.description && (
                  <p className="mt-0.5 text-[13px] leading-relaxed text-ink-600">
                    {toast.description}
                  </p>
                )}
                {toast.action && (
                  <button
                    type="button"
                    onClick={() => {
                      toast.action?.onClick();
                      dismiss(toast.id);
                    }}
                    className="mt-2 text-[13px] font-semibold text-brand-700 underline-offset-2 hover:underline"
                  >
                    {toast.action.label}
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="-mr-1 -mt-1 rounded-control p-1 text-ink-400 transition-colors hover:text-ink-700"
              >
                <X aria-hidden className="size-3.5" />
                <span className="sr-only">Dismiss</span>
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside a ToastProvider");
  }
  return context;
}

/**
 * Report a failed `ApiError` through a toast.
 *
 * The message comes from the server verbatim. Swallowing it in favour of
 * "Something went wrong" is what makes an app impossible to support.
 */
export function useErrorToast() {
  const toast = useToast();
  return useCallback(
    (error: ApiError, fallbackTitle = "Request failed") => {
      toast.error(fallbackTitle, error.message);
    },
    [toast],
  );
}