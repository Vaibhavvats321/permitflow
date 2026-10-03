"use client";

import {
  AlertTriangle,
  Ban,
  FileQuestion,
  Inbox,
  Lock,
  SearchX,
  ServerCrash,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Button } from "./button";

/**
 * Empty and error states.
 *
 * These are the screens a user sees most often in an operations tool — an
 * application that has not been submitted, a queue with nothing assigned, a token
 * that expired — so they get real copy and a real next action. A grey "No data"
 * line wastes the one moment where the interface could explain what to do next.
 */

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  /** Tighter padding, for an empty state inside a table or panel. */
  compact?: boolean;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-6 py-10" : "gap-3 px-6 py-16",
        className,
      )}
    >
      <span className="flex size-11 items-center justify-center rounded-full border border-line bg-surface-muted">
        <Icon aria-hidden className="size-5 text-ink-400" />
      </span>
      <div className="max-w-sm space-y-1.5">
        <p className="text-sm font-semibold text-ink-900">{title}</p>
        {description && (
          <p className="text-[13px] leading-relaxed text-ink-500">{description}</p>
        )}
      </div>
      {action && <div className="mt-1 flex items-center gap-2">{action}</div>}
    </div>
  );
}

export function NoApplicationsEmptyState({ action }: { action?: ReactNode }) {
  return (
    <EmptyState
      icon={FileQuestion}
      title="No permit applications yet"
      description={
        <>
          Start an application for an event in your city. It stays a private draft
          until you submit it for review.
        </>
      }
      action={action}
    />
  );
}

export function NoMatchingFiltersEmptyState({ onClear }: { onClear: () => void }) {
  return (
    <EmptyState
      icon={SearchX}
      title="No applications match these filters"
      description="Try widening the status or event type, or clear the filters to see everything."
      compact
      action={
        <Button variant="subtle" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      }
    />
  );
}

export function EmptyQueueState() {
  return (
    <EmptyState
      icon={Inbox}
      title="Your review queue is clear"
      description="Nothing is waiting on your agency right now. New assignments will appear here as soon as organizers submit them."
    />
  );
}

export function EmptyQueueFilteredState({ onClear }: { onClear: () => void }) {
  return (
    <EmptyState
      icon={SearchX}
      title="No tasks match these filters"
      description="Nothing in your agency's queue has this status or event type."
      compact
      action={
        <Button variant="subtle" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      }
    />
  );
}

export function NoHistoryState() {
  return (
    <EmptyState
      icon={FileQuestion}
      title="No activity recorded yet"
      description="Submissions, edits and agency decisions will appear here as they happen."
      compact
    />
  );
}

/* --- Errors --------------------------------------------------------------- */

const ERROR_PRESENTATION: Record<
  string,
  { icon: LucideIcon; title: string; description: (message: string) => string }
> = {
  forbidden: {
    icon: Lock,
    title: "You do not have access to this",
    description: (message) =>
      message ||
      "This account is not permitted to view this resource. If you think that is wrong, contact your city administrator.",
  },
  unauthenticated: {
    icon: Lock,
    title: "Your session has expired",
    description: () =>
      "PermitFlow sessions last 60 minutes. Sign in again to pick up where you left off.",
  },
  notFound: {
    icon: SearchX,
    title: "Not found",
    description: () =>
      "This resource does not exist, or it is not visible to your account.",
  },
  network: {
    icon: WifiOff,
    title: "Cannot reach the API",
    description: (message) =>
      `${message} Confirm the backend is running on port 8000 and that this site is served from http://localhost:3000, which is the origin its CORS policy allows.`,
  },
  server: {
    icon: ServerCrash,
    title: "Something went wrong on the server",
    description: (message) =>
      `${message} This is a fault on our side rather than something you did — retrying is safe.`,
  },
  generic: {
    icon: AlertTriangle,
    title: "Something went wrong",
    description: (message) => message,
  },
};

/**
 * Map an `ApiError` to copy that explains it and says what to do.
 *
 * The status code chooses the branch, so a 401 never renders as "server error"
 * and a 403 never renders as a network fault. Retrying is offered only where
 * retrying can actually help.
 */
export function ErrorState({
  error,
  onRetry,
  className,
  compact = false,
}: {
  error: ApiError;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const key = error.isNetwork
    ? "network"
    : error.isUnauthenticated
      ? "unauthenticated"
      : error.isForbidden
        ? "forbidden"
        : error.isNotFound
          ? "notFound"
          : error.status >= 500
            ? "server"
            : "generic";

  const presentation = ERROR_PRESENTATION[key];
  const Icon = presentation.icon;

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-6 py-10" : "gap-3 px-6 py-16",
        className,
      )}
    >
      <span className="flex size-11 items-center justify-center rounded-full border border-critical/20 bg-critical-soft">
        <Icon aria-hidden className="size-5 text-critical" />
      </span>
      <div className="max-w-md space-y-1.5">
        <p className="text-sm font-semibold text-ink-900">{presentation.title}</p>
        <p className="text-[13px] leading-relaxed text-ink-500">
          {presentation.description(error.message)}
        </p>
      </div>
      {onRetry && key !== "forbidden" && key !== "notFound" && (
        <div className="mt-1">
          <Button variant="default" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}

/** An inline, non-blocking error for a failed action next to its button. */
export function InlineError({ error, className }: { error: ApiError; className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-control border border-critical/20 bg-critical-soft px-3 py-2.5",
        "text-[13px] leading-relaxed text-critical-ink",
        className,
      )}
    >
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>{error.message}</span>
    </div>
  );
}

/** A 403 presented as a full page, for a role hitting a route it cannot use. */
export function ForbiddenPage() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center text-center">
      <span className="flex size-12 items-center justify-center rounded-full border border-line bg-surface">
        <Ban aria-hidden className="size-6 text-ink-400" />
      </span>
      <h1 className="mt-5 text-lg font-semibold tracking-tight text-ink-900">
        This workspace is not available for your role
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">
        Your account is signed in, but it does not have access to this area of
        PermitFlow. Contact your city administrator if you believe this is a mistake.
      </p>
    </div>
  );
}