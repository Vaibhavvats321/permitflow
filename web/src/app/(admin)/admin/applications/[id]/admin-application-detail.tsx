"use client";

import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock,
  Flame,
  MessageSquare,
  Pencil,
} from "lucide-react";
import { useCallback } from "react";
import { useParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import { getAdminApplication, getAdminApplicationHistory } from "@/lib/endpoints";
import {
  formatDate,
  formatDateRange,
  formatNumber,
  formatRelative,
} from "@/lib/format";
import { applicationStatus, isEditable, reviewStatus } from "@/lib/status";
import type {
  AdminApplicationHistoryResponse,
  AgencyReviewStatus,
  ApplicationResponse,
} from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/cn";
import { StatusBadge } from "@/components/ui/badge";
import { Card, DetailList, DetailRow, Panel } from "@/components/ui/card";
import { ErrorState, NoHistoryState } from "@/components/ui/empty-state";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/primitives";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import {
  ReviewProgressBar,
  ReviewProgressLegend,
  countReviewStates,
} from "@/components/applications/stat-cards";
import { HistoryTimeline } from "@/components/applications/history-timeline";

/**
 * Application detail, as the City Admin sees it.
 *
 * Read-only by construction: it calls only the admin-scoped endpoints, and no
 * edit, submit or resubmit control is rendered — those belong to the
 * organizer who filed the application, and the organizer-scoped APIs would
 * refuse this role with a 403 anyway. The page answers the admin's questions
 * in order: what is this event, what is its status, what did each agency
 * decide, and what has happened to it.
 */
export function AdminApplicationDetail() {
  const token = useToken();
  const params = useParams<{ id: string }>();
  const applicationId = params.id;

  const application = useApi<ApplicationResponse>(
    useCallback(
      (signal) => getAdminApplication(applicationId, { token, signal }),
      [token, applicationId],
    ),
    [token, applicationId],
  );

  const { data, error, isLoading, reload } = application;

  if (isLoading) return <DetailSkeleton />;

  if (error) {
    return (
      <>
        <PageHeader
          title="Application"
          crumbs={[
            { label: "Dashboard", href: "/admin-dashboard" },
            { label: "Applications", href: "/admin/applications" },
            { label: "Not found" },
          ]}
        />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }

  // Destructuring lets TypeScript narrow `data` across the returns above. The
  // remaining possibility — neither loading, nor error, nor any data — is a bug
  // in the hook, so it fails here rather than rendering a screen of `undefined`.
  if (!data) {
    return (
      <>
        <PageHeader title="Application" />
        <PageBody>
          <ErrorState
            error={new ApiError(0, "The application could not be loaded.")}
            onRetry={reload}
          />
        </PageBody>
      </>
    );
  }

  const presentation = applicationStatus(data.status);
  const { approved, pending, blocked } = countReviewStates(data.reviews);
  const feedbackCount = data.reviews.filter(
    (review) => review.comment && review.comment.trim().length > 0,
  ).length;

  return (
    <>
      <PageHeader
        title={data.event_name}
        crumbs={[
          { label: "Dashboard", href: "/admin-dashboard" },
          { label: "Applications", href: "/admin/applications" },
          { label: data.event_name },
        ]}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <StatusBadge presentation={presentation} />
          <span className="text-[13px] text-ink-500">{data.event_type}</span>
          <span aria-hidden className="text-ink-300">
            ·
          </span>
          <span className="text-[13px] text-ink-500">
            Created {formatDate(data.created_at)}
          </span>
          <span aria-hidden className="text-ink-300">
            ·
          </span>
          <span className="text-[13px] text-ink-500">
            Updated {formatRelative(data.updated_at)}
          </span>
        </div>
      </PageHeader>

      <PageBody>
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Panel title="Application details" bodyClassName="px-5 pb-2 pt-1">
                <DetailList>
                  <DetailRow label="Event name">{data.event_name}</DetailRow>
                  <DetailRow label="Event type">{data.event_type}</DetailRow>
                  <DetailRow label="Dates">
                    {formatDateRange(data.start_date, data.end_date)}
                    {data.start_date && data.end_date && data.start_date !== data.end_date && (
                      <span className="mt-0.5 block text-[13px] text-ink-500">
                        Starts {formatDate(data.start_date)} at{" "}
                        {new Date(data.start_date).toLocaleTimeString(undefined, {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </span>
                    )}
                  </DetailRow>
                  <DetailRow label="Location">
                    {data.location ?? <span className="text-ink-400">Not set</span>}
                  </DetailRow>
                  <DetailRow label="Expected attendance">
                    {data.expected_attendance !== null ? (
                      <>
                        <span className="tabular">
                          {formatNumber(data.expected_attendance)} people
                        </span>
                        {data.expected_attendance > 5000 && (
                          <span className="mt-1.5 flex items-center gap-1.5 text-[13px] text-attention-ink">
                            <Flame aria-hidden className="size-3.5 shrink-0" />
                            Large event — fire review added automatically
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-ink-400">Not set</span>
                    )}
                  </DetailRow>
                  <DetailRow label="Description">
                    {data.description ? (
                      <p className="whitespace-pre-line leading-relaxed">{data.description}</p>
                    ) : (
                      <span className="text-ink-400">No description provided</span>
                    )}
                  </DetailRow>
                </DetailList>
              </Panel>
            </div>

            <div className="space-y-5">
              {/* Status explainer: what the status means and what happens next. */}
              <Card>
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden
                    className={cn(
                      "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
                      presentation.tone === "positive" && "bg-positive-soft text-positive",
                      presentation.tone === "critical" && "bg-critical-soft text-critical",
                      presentation.tone === "attention" && "bg-attention-soft text-attention",
                      presentation.tone === "progress" && "bg-brand-50 text-brand-600",
                      presentation.tone === "info" && "bg-info-soft text-info",
                      presentation.tone === "neutral" && "bg-ink-100 text-ink-500",
                    )}
                  >
                    {data.status === "Approved" ? (
                      <CheckCircle2 aria-hidden className="size-4" />
                    ) : data.status === "Rejected" ? (
                      <AlertTriangle aria-hidden className="size-4" />
                    ) : data.status === "Changes Requested" ? (
                      <MessageSquare aria-hidden className="size-4" />
                    ) : data.status === "Draft" ? (
                      <Pencil aria-hidden className="size-4" />
                    ) : (
                      <Clock aria-hidden className="size-4" />
                    )}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink-900">
                      {presentation.label}
                    </p>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-600">
                      {presentation.description}
                    </p>
                  </div>
                </div>

                {data.reviews.length > 0 && (
                  <>
                    <Separator className="my-4" />
                    <div className="space-y-2">
                      <ReviewProgressBar
                        total={data.reviews.length}
                        approved={approved}
                        pending={pending}
                        blocked={blocked}
                      />
                      <ReviewProgressLegend
                        approved={approved}
                        pending={pending}
                        blocked={blocked}
                      />
                      {feedbackCount > 0 && (
                        <p className="text-[13px] leading-relaxed text-ink-500">
                          {feedbackCount} {feedbackCount === 1 ? "agency has" : "agencies have"}{" "}
                          left a comment. Read them under Agency reviews below.
                        </p>
                      )}
                    </div>
                  </>
                )}

                {isEditable(data.status) && (
                  <>
                    <Separator className="my-4" />
                    <p className="text-[13px] leading-relaxed text-ink-500">
                      This application can still be changed. Editing and resubmitting are
                      done by the organizer who filed it — this admin view is read-only.
                    </p>
                  </>
                )}
              </Card>

              <Card>
                <p className="text-[13px] leading-relaxed text-ink-500">
                  {data.status === "Submitted" || data.status === "Under Review"
                    ? "Agencies are reviewing this application. Their decisions are recorded against it and reflected in the status above."
                    : data.status === "Approved"
                      ? "Every required agency approved this application, so the permit is cleared."
                      : data.status === "Rejected"
                        ? "An agency declined this application. The rejection comment is with the organizer."
                        : data.status === "Changes Requested"
                          ? "An agency asked the organizer for corrections. The application waits on the organizer, not the city."
                          : "The organizer has not submitted this application for review yet."}
                </p>
              </Card>
            </div>
          </div>

          <AgencyReviewsPanel
            reviews={data.reviews}
            status={data.status}
            eventName={data.event_name}
          />

          <HistoryPanel token={token} applicationId={applicationId} />
        </div>
      </PageBody>
    </>
  );
}

/* --- Agency reviews ------------------------------------------------------- */

/**
 * Each required agency's decision, straight from the detail endpoint's
 * `reviews` array — same rows and same presentation the organizer sees, because
 * the data is identical. Only the empty-state copy differs: the admin is the
 * one who configures routing, so the admin copy speaks to the city's rules.
 */
function AgencyReviewsPanel({
  reviews,
  status,
  eventName,
}: {
  reviews: AgencyReviewStatus[];
  status: ApplicationResponse["status"];
  eventName: string;
}) {
  if (status === "Draft" || reviews.length === 0) {
    return (
      <Panel title="Agency reviews" bodyClassName="p-0">
        <div className="px-5 py-10 text-center">
          <span className="mx-auto flex size-11 items-center justify-center rounded-full border border-line bg-surface-muted">
            <Building2 aria-hidden className="size-5 text-ink-400" />
          </span>
          <p className="mt-4 text-sm font-semibold text-ink-900">
            {status === "Draft" ? "Not submitted yet" : "No agencies assigned"}
          </p>
          <p className="mx-auto mt-1.5 max-w-sm text-[13px] leading-relaxed text-ink-500">
            {status === "Draft"
              ? `${eventName} is still a draft, so no agency has been asked to review it.`
              : "The city's routing rules do not require any agency for this event type."}
          </p>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Agency reviews"
      description="What each required agency decided, when it was assigned, and the comment it left."
      bodyClassName="p-0"
    >
      <ul className="divide-y divide-line">
        {reviews.map((review) => {
          const presentation = reviewStatus(review.review_status);
          const hasComment = Boolean(review.comment?.trim());
          const wasResent =
            new Date(review.updated_at).getTime() >
            new Date(review.created_at).getTime() + 1000;

          return (
            <li key={review.agency_id} className="px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-control border border-line bg-surface-muted">
                    <Building2 aria-hidden className="size-3.5 text-ink-500" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink-900">
                      {review.agency_name}
                    </p>
                    <p className="mt-0.5 text-[12px] text-ink-400">
                      Assigned {formatDate(review.created_at)}
                      {wasResent && " · asked again after resubmission"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <StatusBadge presentation={presentation} size="sm" />
                  {presentation.tone !== "progress" && presentation.tone !== "neutral" && (
                    <span className="tabular whitespace-nowrap text-[12px] text-ink-400">
                      {formatDate(review.updated_at)}
                    </span>
                  )}
                </div>
              </div>

              {hasComment ? (
                <blockquote
                  className={cn(
                    "mt-3 rounded-control border-l-2 bg-surface-muted px-3.5 py-2.5",
                    "text-[13px] leading-relaxed text-ink-700",
                    presentation.tone === "critical"
                      ? "border-critical/40"
                      : presentation.tone === "attention"
                        ? "border-attention/40"
                        : "border-positive/40",
                  )}
                >
                  {review.comment}
                </blockquote>
              ) : (
                <p className="mt-3 text-[13px] italic text-ink-400">
                  {presentation.tone === "progress"
                    ? "Awaiting this agency's decision."
                    : "No comment was left with this decision."}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="border-t border-line px-5 py-3.5 text-[13px] leading-relaxed text-ink-500">
        Agencies are listed by name as your city configured them. Individual
        reviewers are not named here; the activity timeline below records who
        recorded each decision.
      </div>
    </Panel>
  );
}

/* --- Activity ------------------------------------------------------------- */

/**
 * The audit timeline, fetched independently of the application so that a
 * history failure degrades this one section — with a retry — instead of
 * blanking a page whose main data loaded fine.
 */
function HistoryPanel({
  token,
  applicationId,
}: {
  token: string;
  applicationId: string;
}) {
  const history = useApi<AdminApplicationHistoryResponse>(
    useCallback(
      (signal) => getAdminApplicationHistory(applicationId, { token, signal }),
      [token, applicationId],
    ),
    [token, applicationId],
  );

  if (history.isLoading) {
    return (
      <Panel>
        <div className="space-y-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="flex gap-4">
              <Skeleton className="size-7 shrink-0 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-40" />
                <SkeletonText lines={1} />
              </div>
            </div>
          ))}
        </div>
      </Panel>
    );
  }

  if (history.error) {
    return (
      <Panel bodyClassName="p-0">
        <ErrorState error={history.error} onRetry={history.reload} compact />
      </Panel>
    );
  }

  if (!history.data || history.data.events.length === 0) {
    return (
      <Panel bodyClassName="p-0">
        <NoHistoryState />
      </Panel>
    );
  }

  return <HistoryTimeline history={history.data} viewer="admin" />;
}

/* --- Skeleton ------------------------------------------------------------- */

function DetailSkeleton() {
  return (
    <>
      <PageHeader title="Loading application…" />
      <PageBody>
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Panel>
              <div className="space-y-5">
                {Array.from({ length: 6 }, (_, index) => (
                  <div key={index} className="space-y-2">
                    <Skeleton className="h-3 w-28" />
                    <Skeleton className="h-3.5 w-2/3" />
                  </div>
                ))}
              </div>
            </Panel>
          </div>
          <Panel>
            <SkeletonText lines={4} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
