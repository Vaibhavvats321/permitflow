"use client";

import { Circle } from "lucide-react";
import { formatDateTime, formatRelative, humanizeAction } from "@/lib/format";
import { applicationStatus, auditPresentation, toneDotClass } from "@/lib/status";
import type {
  AdminAuditEvent,
  AdminApplicationHistoryResponse,
  ApplicationHistoryResponse,
} from "@/lib/types";
import { cn } from "@/lib/cn";
import { Panel } from "@/components/ui/card";

/**
 * The audit timeline, shared by all three roles.
 *
 * Organizer, reviewer and admin histories come from different endpoints but
 * return the same event shape — the admin's being a strict superset with actor
 * email and agency name — so they render through the same component. Two copies
 * would be two chances for the timeline to disagree about what an event means.
 *
 * The `viewer` prop drives two differences:
 *
 * - An agency does not need to see an organizer editing a draft, so the
 *   reviewer's copy filters those out.
 * - The admin copy shows who recorded each event (actor email, agency name)
 *   where the endpoint supplied it; organizer and reviewer endpoints do not
 *   send those fields, so those viewers keep the role-hint footer.
 */

type Viewer = "organizer" | "reviewer" | "admin";

const KIND_COLOR: Record<string, string> = {
  neutral: "bg-ink-300",
  positive: "bg-positive",
  critical: "bg-critical",
  attention: "bg-attention",
  info: "bg-info",
};

/** Events only the organizer's history is expected to contain. */
function isOrganizerEvent(action: string): boolean {
  return action.startsWith("application.");
}

export function HistoryTimeline({
  history,
  viewer,
}: {
  history: ApplicationHistoryResponse | AdminApplicationHistoryResponse;
  viewer: Viewer;
}) {
  // Widened once here: the admin response's events are a superset of the
  // shared `AuditEvent`, and `AuditEvent[]` is assignable to it, so the union
  // above collapses to one working type for the rest of the component.
  const allEvents: AdminAuditEvent[] = history.events;

  const events =
    viewer === "reviewer"
      ? allEvents.filter((event) => !isOrganizerEvent(event.action))
      : allEvents;

  if (events.length === 0) {
    return (
      <Panel bodyClassName="p-0">
        <div className="px-5 py-10 text-center">
          <p className="text-sm font-semibold text-ink-900">No decisions recorded yet</p>
          <p className="mx-auto mt-1.5 max-w-sm text-[13px] leading-relaxed text-ink-500">
            Nothing has happened on this application&rsquo;s review. Agency decisions
            will appear here with their comments.
          </p>
        </div>
      </Panel>
    );
  }

  const currentStatus = applicationStatus(history.application_status);

  return (
    <Panel
      title="Activity"
      description={`${events.length} ${events.length === 1 ? "entry" : "entries"}, most recent last.`}
      bodyClassName="px-5 py-5"
    >
      <ol className="relative space-y-0">
        {events.map((event, index) => (
          <TimelineEntry
            key={event.id}
            event={event}
            isLast={index === events.length - 1}
            viewer={viewer}
          />
        ))}
      </ol>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-line pt-4">
        <span className="text-[13px] text-ink-500">Current status</span>
        <span className="flex items-center gap-2">
          <span
            aria-hidden
            className={cn("size-1.5 rounded-full", toneDotClass(currentStatus.tone))}
          />
          <span className="text-[13px] font-medium text-ink-800">{currentStatus.label}</span>
        </span>
      </div>
    </Panel>
  );
}

function TimelineEntry({
  event,
  isLast,
  viewer,
}: {
  event: AdminAuditEvent;
  isLast: boolean;
  viewer: Viewer;
}) {
  const presentation = auditPresentation(event.action);
  const statusChanged = event.old_status !== event.new_status;
  const hasComment = Boolean(event.comment?.trim());

  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      {/* Rail: a dot plus the connecting line, omitted on the final entry so the
          timeline does not appear to continue past its end. */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute left-[11px] top-7 h-[calc(100%-1.75rem)] w-px bg-line"
        />
      )}

      <span
        aria-hidden
        className={cn(
          "relative z-10 mt-1 flex size-6 shrink-0 items-center justify-center rounded-full",
          "ring-4 ring-surface",
        )}
      >
        <Circle
          className={cn(
            "size-3",
            KIND_COLOR[presentation.kind] ?? "bg-ink-300",
            "fill-current",
          )}
          strokeWidth={0}
        />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <p className="text-[13px] font-medium text-ink-900">
            {presentation.kind !== "neutral" ? presentation.label : humanizeAction(event.action)}
          </p>
          <time
            dateTime={event.created_at}
            title={formatDateTime(event.created_at)}
            className="whitespace-nowrap text-[12px] text-ink-400"
          >
            {formatRelative(event.created_at)}
          </time>
        </div>

        {statusChanged && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {event.old_status && (
              <span className="rounded border border-line bg-surface-muted px-1.5 py-0.5 text-[11px] text-ink-500">
                {event.old_status}
              </span>
            )}
            <span aria-hidden className="text-[11px] text-ink-300">
              &rarr;
            </span>
            {event.new_status && (
              <span className="rounded border border-line-strong bg-surface px-1.5 py-0.5 text-[11px] font-medium text-ink-700">
                {event.new_status}
              </span>
            )}
          </div>
        )}

        {hasComment && (
          <p className="mt-2 whitespace-pre-line border-l-2 border-line pl-3 text-[13px] leading-relaxed text-ink-600">
            {event.comment}
          </p>
        )}

        {/* Attribution. Organizer and reviewer endpoints carry `user_id` but no
            name, so those views get a role hint rather than a person — and an
            admin view shows the actor email and agency name the admin history
            endpoint supplies, falling back to a neutral label when a system
            event (or a vanished user row) left no actor to name. */}
        {viewer === "admin" ? (
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-400">
            <span className={event.actor_email ? "font-medium text-ink-500" : undefined}>
              {event.actor_email ?? (event.user_id ? "Unknown user" : "System")}
            </span>
            {event.agency_name && (
              <>
                <span aria-hidden className="text-ink-300">
                  ·
                </span>
                <span>{event.agency_name}</span>
              </>
            )}
          </p>
        ) : (
          <p className="mt-2 text-[11px] text-ink-400">
            {event.agency_id
              ? "Recorded by the agency"
              : viewer === "reviewer"
                ? "Recorded by the organizer"
                : "Recorded by you"}
          </p>
        )}
      </div>
    </li>
  );
}