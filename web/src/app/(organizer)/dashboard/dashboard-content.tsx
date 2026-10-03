"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Inbox,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo } from "react";
import { useToken } from "@/lib/auth";
import { listApplications } from "@/lib/endpoints";
import { formatDateRange, formatRelative } from "@/lib/format";
import { daysPending, summarize } from "@/lib/summary";
import { applicationStatus, toneDotClass } from "@/lib/status";
import { cn } from "@/lib/cn";
import { APPLICATION_STATUSES, type ApplicationResponse } from "@/lib/types";
import { PageSize } from "@/lib/constants";
import { useApi } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/card";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { SkeletonCard, SkeletonRows } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/primitives";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import {
  ReviewProgressBar,
  ReviewProgressLegend,
  StatCards,
  countReviewStates,
  type Stat,
} from "@/components/applications/stat-cards";

/**
 * The organizer dashboard.
 *
 * Answers "what needs me" first, then "what is moving", then "what just
 * happened" — in that order, because that is the order an organizer arrives with.
 *
 * Everything here is derived from one `GET /applications` call. No stats
 * endpoint exists and none was added; see `lib/summary.ts` for why that is the
 * right trade.
 */
export function OrganizerDashboard() {
  const token = useToken();

  const { data, error, isLoading, reload } = useApi<ApplicationResponse[]>(
    useCallback(
      (signal) =>
        listApplications({ limit: PageSize }, { token, signal }),
      [token],
    ),
    [token],
  );

  const summary = useMemo(() => summarize(data ?? []), [data]);

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" description="Your permit applications at a glance." />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }

  const stats: Stat[] = [
    {
      label: "Needs your attention",
      value: summary.needsAction.length,
      hint:
        summary.counts["Changes Requested"] > 0
          ? `${summary.counts["Changes Requested"]} sent back for changes`
          : summary.unsubmitted > 0
            ? `${summary.unsubmitted} ${summary.unsubmitted === 1 ? "draft" : "drafts"} in progress`
            : "Nothing outstanding",
      href: "/applications?status=Changes+Requested",
      tone: summary.counts["Changes Requested"] > 0 ? "attention" : "neutral",
      icon: AlertCircle,
    },
    {
      label: "In review",
      value: summary.counts.Submitted + summary.counts["Under Review"],
      hint: "With agencies now",
      href: "/applications?status=Under+Review",
      tone: "progress",
      icon: Clock,
    },
    {
      label: "Approved",
      value: summary.counts.Approved,
      hint: "Cleared for their event dates",
      href: "/applications?status=Approved",
      tone: "positive",
      icon: CheckCircle2,
    },
    {
      label: "Drafts",
      value: summary.unsubmitted,
      hint: "Not sent to any agency",
      href: "/applications?status=Draft",
      tone: "neutral",
      icon: FileText,
    },
  ];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Where your permit applications stand with each agency."
        actions={
          <Button asChild variant="primary">
            <Link href="/applications/new">
              New application
              <ArrowRight aria-hidden />
            </Link>
          </Button>
        }
      />

      <PageBody className="space-y-6">
        {isLoading ? (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <SkeletonCard key={index} />
              ))}
            </div>
            <div className="rounded-card border border-line bg-surface">
              <SkeletonRows rows={4} columns={3} />
            </div>
          </>
        ) : (
          <>
            <StatCards stats={stats} />

            <div className="grid gap-6 lg:grid-cols-3">
              <NeedsAction summary={summary} />
              <AwaitingDecision summary={summary} />
              <RecentlyUpdated summary={summary} />
            </div>

            <StatusBreakdown counts={summary.counts} averageAgencies={summary.averageAgencies} />
          </>
        )}
      </PageBody>
    </>
  );
}

/* --- Panels --------------------------------------------------------------- */

function NeedsAction({
  summary,
}: {
  summary: ReturnType<typeof summarize>;
}) {
  return (
    <Panel
      title="Needs your attention"
      description="Drafts to finish, and applications sent back for changes."
      bodyClassName="p-0"
    >
      {summary.needsAction.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          compact
          title="Nothing waiting on you"
          description="Every application is either with an agency or already decided."
        />
      ) : (
        <ul className="divide-y divide-line">
          {summary.needsAction.map((application) => {
            const presentation = applicationStatus(application.status);
            const isChanges = application.status === "Changes Requested";
            const feedback = application.reviews.find(
              (review) => review.comment && review.review_status === "Changes Requested",
            );

            return (
              <li key={application.id}>
                <Link
                  href={`/applications/${application.id}`}
                  className="group block px-5 py-4 transition-colors hover:bg-surface-muted"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink-900 group-hover:text-brand-700">
                      {application.event_name}
                    </p>
                    <StatusBadge presentation={presentation} size="sm" />
                  </div>

                  <p className="mt-1 text-[13px] text-ink-500">
                    {isChanges && feedback?.agency_name
                      ? `${feedback.agency_name} requested changes`
                      : "Draft — not yet submitted"}
                  </p>

                  {feedback?.comment && (
                    <p className="mt-2 line-clamp-2 border-l-2 border-attention/40 pl-3 text-[13px] leading-relaxed text-ink-600">
                      {feedback.comment}
                    </p>
                  )}

                  <p className="mt-2 text-[12px] text-ink-400">
                    Updated {formatRelative(application.updated_at)}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function AwaitingDecision({
  summary,
}: {
  summary: ReturnType<typeof summarize>;
}) {
  return (
    <Panel
      title="Longest outstanding"
      description="Applications where an agency has not yet decided."
      bodyClassName="p-0"
    >
      {summary.awaitingDecision.length === 0 ? (
        <EmptyState
          icon={Inbox}
          compact
          title="No decisions pending"
          description="Nothing is sitting with an agency right now."
        />
      ) : (
        <ul className="divide-y divide-line">
          {summary.awaitingDecision.map((application) => {
            const waiting = daysPending(application);
            const { pending } = countReviewStates(application.reviews);
            // Three days is the point at which a chase is worth making; the
            // threshold highlights rather than shames.
            const isSlow = waiting >= 3;

            return (
              <li key={application.id}>
                <Link
                  href={`/applications/${application.id}`}
                  className="group block px-5 py-4 transition-colors hover:bg-surface-muted"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink-900 group-hover:text-brand-700">
                      {application.event_name}
                    </p>
                    {isSlow && (
                      <Badge tone="attention" size="sm">
                        {waiting}d waiting
                      </Badge>
                    )}
                  </div>

                  <p className="tabular mt-1 text-[13px] text-ink-500">
                    {pending} {pending === 1 ? "agency" : "agencies"} still to respond
                  </p>

                  <p className="mt-2 text-[12px] text-ink-400">
                    {formatDateRange(application.start_date, application.end_date)}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function RecentlyUpdated({
  summary,
}: {
  summary: ReturnType<typeof summarize>;
}) {
  return (
    <Panel
      title="Recently updated"
      action={
        <Button asChild variant="ghost" size="sm">
          <Link href="/applications">View all</Link>
        </Button>
      }
      bodyClassName="p-0"
    >
      {summary.recent.length === 0 ? (
        <EmptyState
          icon={FileText}
          compact
          title="No applications yet"
          description="Your first application will appear here."
          action={
            <Button asChild variant="subtle" size="sm">
              <Link href="/applications/new">Start one</Link>
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-line">
          {summary.recent.map((application) => {
            const presentation = applicationStatus(application.status);
            const { approved, pending, blocked } = countReviewStates(application.reviews);

            return (
              <li key={application.id}>
                <Link
                  href={`/applications/${application.id}`}
                  className="group block px-5 py-3.5 transition-colors hover:bg-surface-muted"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink-900 group-hover:text-brand-700">
                      {application.event_name}
                    </p>
                    <StatusBadge presentation={presentation} size="sm" dot={false} />
                  </div>

                  {application.reviews.length > 0 && (
                    <div className="mt-2.5 space-y-1.5">
                      <ReviewProgressBar
                        total={application.reviews.length}
                        approved={approved}
                        pending={pending}
                        blocked={blocked}
                      />
                      <ReviewProgressLegend
                        approved={approved}
                        pending={pending}
                        blocked={blocked}
                      />
                    </div>
                  )}

                  <p className="mt-2 text-[12px] text-ink-400">
                    Updated {formatRelative(application.updated_at)}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function StatusBreakdown({
  counts,
  averageAgencies,
}: {
  counts: ReturnType<typeof summarize>["counts"];
  averageAgencies: number | null;
}) {
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const hasAgencyFeedback = counts["Changes Requested"] + counts.Rejected;

  return (
    <Panel
      title="All applications"
      description={
        total === 0
          ? "Nothing here yet."
          : `Across ${total} ${total === 1 ? "application" : "applications"}${
              averageAgencies !== null
                ? `, averaging ${averageAgencies.toFixed(1)} agencies each`
                : ""
            }.`
      }
      action={
        <Button asChild variant="default" size="sm">
          <Link href="/applications">Open applications</Link>
        </Button>
      }
      bodyClassName="p-0"
    >
      <div className="grid grid-cols-2 divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
        {APPLICATION_STATUSES.map((status) => {
          const presentation = applicationStatus(status);
          const count = counts[status];

          return (
            <Link
              key={status}
              href={`/applications?status=${encodeURIComponent(status)}`}
              className="group px-5 py-4 transition-colors hover:bg-surface-muted"
            >
              {/*
                The dot colour comes from the shared tone map via `toneDotClass`,
                so this status marker cannot drift from the badge of the same
                status elsewhere.
              */}
              <div className="flex items-center gap-1.5">
                <span aria-hidden className={cn("size-1.5 rounded-full", toneDotClass(presentation.tone))} />
                <p className="truncate text-[12px] font-medium text-ink-500">
                  {presentation.label}
                </p>
              </div>
              <p className="tabular mt-2 text-2xl font-semibold tracking-tight text-ink-950">
                {count}
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-ink-400 opacity-0 transition-opacity group-hover:opacity-100">
                {presentation.description.split(".")[0]}
              </p>
            </Link>
          );
        })}
      </div>

      {hasAgencyFeedback > 0 && (
        <>
          <Separator />
          <p className="px-5 py-3.5 text-[13px] text-ink-500">
            {hasAgencyFeedback} of your applications carry agency feedback. Those
            comments are in each application&rsquo;s Reviews tab.
          </p>
        </>
      )}
    </Panel>
  );
}