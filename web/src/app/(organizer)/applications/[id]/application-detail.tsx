"use client";

import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock,
  Flame,
  MessageSquare,
  Pencil,
  RotateCcw,
  Send,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import {
  getApplication,
  getApplicationHistory,
  resubmitApplication,
  submitApplication,
} from "@/lib/endpoints";
import {
  formatDate,
  formatDateRange,
  formatNumber,
  formatRelative,
} from "@/lib/format";
import {
  applicationStatus,
  canResubmit,
  canSubmit,
  isEditable,
  reviewStatus,
} from "@/lib/status";
import type {
  AgencyReviewStatus,
  ApplicationHistoryResponse,
  ApplicationResponse,
  ResubmitApplicationResponse,
  SubmitApplicationResponse,
} from "@/lib/types";
import { useApi, useMutation } from "@/lib/use-api";
import { cn } from "@/lib/cn";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, DetailList, DetailRow, Panel } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { ErrorState, InlineError, NoHistoryState } from "@/components/ui/empty-state";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { ReviewProgressBar, ReviewProgressLegend, countReviewStates } from "@/components/applications/stat-cards";
import { HistoryTimeline } from "@/components/applications/history-timeline";

/**
 * Application detail.
 *
 * The organizer arrives here with one of three questions, and the three tabs
 * answer them: what does this say (Overview), what is each agency doing (Reviews),
 * and what has happened to it (History).
 *
 * Which actions are offered is derived entirely from the server-reported status,
 * via `isEditable` / `canSubmit` / `canResubmit`. Those helpers mirror the
 * backend's own transition rules, so the UI cannot present an action the API
 * would refuse with a 409 — and a 409 still renders a readable message if the
 * state moved underneath us.
 */
export function ApplicationDetail() {
  const token = useToken();
  const toast = useToast();
  const params = useParams<{ id: string }>();
  const applicationId = params.id;

  const [submitOpen, setSubmitOpen] = useState(false);
  const [resubmitOpen, setResubmitOpen] = useState(false);

  const application = useApi<ApplicationResponse>(
    useCallback((signal) => getApplication(applicationId, { token, signal }), [token, applicationId]),
    [token, applicationId],
  );

  const { data, error, isLoading, reload, setData } = application;

  if (isLoading) return <DetailSkeleton />;

  if (error) {
    return (
      <>
        <PageHeader
          title="Application"
          crumbs={[{ label: "Applications", href: "/applications" }, { label: "Not found" }]}
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
          { label: "Applications", href: "/applications" },
          { label: data.event_name },
        ]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {isEditable(data.status) && (
              <Button asChild variant="default" icon={<Pencil />}>
                <Link href={`/applications/${data.id}/edit`}>Edit</Link>
              </Button>
            )}
            {canSubmit(data.status) && (
              <Button variant="primary" icon={<Send />} onClick={() => setSubmitOpen(true)}>
                Submit for review
              </Button>
            )}
            {canResubmit(data.status) && (
              <Button
                variant="primary"
                icon={<RotateCcw />}
                onClick={() => setResubmitOpen(true)}
              >
                Resubmit
              </Button>
            )}
          </div>
        }
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
        <Tabs defaultValue="overview">
          <TabsList className="mb-6">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="reviews" count={data.reviews.length}>
              Agency reviews
            </TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>

          {/* --- Overview ---------------------------------------------------- */}
          <TabsContent value="overview" className="space-y-5">
            <div className="grid gap-5 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <Panel
                  title="Application details"
                  action={
                    isEditable(data.status) ? (
                      <Button asChild variant="ghost" size="sm" icon={<Pencil />}>
                        <Link href={`/applications/${data.id}/edit`}>Edit</Link>
                      </Button>
                    ) : undefined
                  }
                  bodyClassName="px-5 pb-2 pt-1"
                >
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
                {/* Status explainer. The single most useful thing on this page:
                    it says what the status means and what happens next. */}
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
                      </div>
                    </>
                  )}

                  {isEditable(data.status) && (
                    <>
                      <Separator className="my-4" />
                      <div className="flex flex-col gap-2">
                        {canSubmit(data.status) && (
                          <Button variant="primary" size="sm" icon={<Send />} onClick={() => setSubmitOpen(true)}>
                            Submit for review
                          </Button>
                        )}
                        {canResubmit(data.status) && (
                          <Button variant="primary" size="sm" icon={<RotateCcw />} onClick={() => setResubmitOpen(true)}>
                            Resubmit to agencies
                          </Button>
                        )}
                        {data.status === "Draft" && (
                          <p className="text-[13px] leading-relaxed text-ink-500">
                            Fill in the dates, location and expected attendance before
                            submitting — agencies cannot assess an incomplete
                            application.
                          </p>
                        )}
                      </div>
                    </>
                  )}

                  {data.status === "Rejected" && (
                    <>
                      <Separator className="my-4" />
                      <p className="text-[13px] leading-relaxed text-critical-ink">
                        A rejected application cannot be resubmitted. The rejection
                        comment is in Agency reviews.
                      </p>
                    </>
                  )}
                </Card>

                {data.status === "Under Review" || data.status === "Submitted" ? (
                  <Card>
                    <p className="text-[13px] leading-relaxed text-ink-500">
                      This application is with {data.reviews.length}{" "}
                      {data.reviews.length === 1 ? "agency" : "agencies"} and cannot be
                      edited while they review it. You will see their decisions here
                      as they arrive.
                    </p>
                  </Card>
                ) : null}
              </div>
            </div>
          </TabsContent>

          {/* --- Reviews ----------------------------------------------------- */}
          <TabsContent value="reviews">
            <AgencyReviewList
              reviews={data.reviews}
              status={data.status}
              eventName={data.event_name}
              feedbackCount={feedbackCount}
            />
          </TabsContent>

          {/* --- History ----------------------------------------------------- */}
          <TabsContent value="history">
            <HistoryPanel token={token} applicationId={data.id} />
          </TabsContent>
        </Tabs>
      </PageBody>

      <SubmitDialog
        open={submitOpen}
        onOpenChange={setSubmitOpen}
        application={data}
        onDone={(result) => {
          setSubmitOpen(false);
          setData(result.application);
          toast.success(
            "Submitted for review",
            `Sent to ${result.required_agencies.length} ${
              result.required_agencies.length === 1 ? "agency" : "agencies"
            }.`,
          );
        }}
      />

      <ResubmitDialog
        open={resubmitOpen}
        onOpenChange={setResubmitOpen}
        applicationId={data.id}
        onDone={(result) => {
          setResubmitOpen(false);
          setData(result.application);
          toast.success(
            "Resubmitted",
            result.reset_agencies.length > 0
              ? `Sent back to ${result.reset_agencies
                  .map((agency) => agency.name)
                  .join(", ")}.`
              : "No agency requested changes, so nothing was resent.",
          );
        }}
      />
    </>
  );
}

/* --- Agency reviews ------------------------------------------------------- */

function AgencyReviewList({
  reviews,
  status,
  eventName,
  feedbackCount,
}: {
  reviews: AgencyReviewStatus[];
  status: ApplicationResponse["status"];
  eventName: string;
  feedbackCount: number;
}) {
  if (status === "Draft") {
    return (
      <Panel bodyClassName="p-0">
        <div className="px-5 py-10 text-center">
          <span className="mx-auto flex size-11 items-center justify-center rounded-full border border-line bg-surface-muted">
            <Building2 aria-hidden className="size-5 text-ink-400" />
          </span>
          <p className="mt-4 text-sm font-semibold text-ink-900">No agencies yet</p>
          <p className="mx-auto mt-1.5 max-w-sm text-[13px] leading-relaxed text-ink-500">
            {eventName} has not been submitted, so no agency has been asked to
            review it. Which agencies are required is decided by your city&rsquo;s
            rules for a {status === "Draft" ? "draft" : status} application and by
            its expected attendance.
          </p>
        </div>
      </Panel>
    );
  }

  if (reviews.length === 0) {
    return (
      <Panel bodyClassName="p-0">
        <div className="px-5 py-10 text-center">
          <p className="text-sm font-semibold text-ink-900">No agencies assigned</p>
          <p className="mt-1.5 text-[13px] text-ink-500">
            Your city has no routing rules configured for this event type.
          </p>
        </div>
      </Panel>
    );
  }

  return (
    <div className="space-y-5">
      {feedbackCount > 0 && (
        <div className="flex items-start gap-3 rounded-card border border-attention/25 bg-attention-soft px-4 py-3.5">
          <MessageSquare aria-hidden className="mt-0.5 size-4 shrink-0 text-attention" />
          <div>
            <p className="text-[13px] font-semibold text-attention-ink">
              {feedbackCount} {feedbackCount === 1 ? "agency has" : "agencies have"} left
              {feedbackCount === 1 ? " a comment" : " comments"}
            </p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-attention-ink/85">
              {canResubmit(status)
                ? "Make the corrections they describe, then resubmit. Only the agencies that asked for changes will be asked again."
                : "Read each comment below to see what the agencies need."}
            </p>
          </div>
        </div>
      )}

      <Panel bodyClassName="p-0">
        <ul className="divide-y divide-line">
          {reviews.map((review) => {
            const presentation = reviewStatus(review.review_status);
            const hasComment = Boolean(review.comment?.trim());
            const wasResent = new Date(review.updated_at).getTime() >
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
      </Panel>

      <p className="px-1 text-[13px] leading-relaxed text-ink-400">
        Agencies are listed by name as your city configured them. Individual
        reviewers are not named on this view; the History tab records who recorded
        each decision.
      </p>
    </div>
  );
}

/* --- History -------------------------------------------------------------- */

function HistoryPanel({
  token,
  applicationId,
}: {
  token: string;
  applicationId: string;
}) {
  const history = useApi<ApplicationHistoryResponse>(
    useCallback(
      (signal) => getApplicationHistory(applicationId, { token, signal }),
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

  return <HistoryTimeline history={history.data} viewer="organizer" />;
}

/* --- Dialogs -------------------------------------------------------------- */

/**
 * Submit confirmation.
 *
 * The dialog states which agencies will be asked and calls out the fire-department
 * override when it applies, because that is the part an organizer is most likely
 * to be surprised by and cannot predict. The list comes from the submit response,
 * so it is only shown after the fact — before that, the copy explains the rule.
 */
function SubmitDialog({
  open,
  onOpenChange,
  application,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  application: ApplicationResponse;
  onDone: (result: SubmitApplicationResponse) => void;
}) {
  const token = useToken();
  const submit = useMutation(() => submitApplication(application.id, { token }));

  const incomplete =
    application.start_date === null ||
    application.end_date === null ||
    !application.location ||
    application.expected_attendance === null;

  const triggersFire = (application.expected_attendance ?? 0) > 5000;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Submit this application for review?"
      confirmLabel="Submit for review"
      tone="primary"
      loading={submit.isPending}
      onConfirm={async () => {
        const result = await submit.run();
        if (result) onDone(result);
      }}
      description={
        <>
          Your city&rsquo;s routing rules decide which agencies review a{" "}
          <span className="font-medium text-ink-800">{application.event_type}</span>{" "}
          application. Each agency decides independently, and this cannot be undone.
        </>
      }
    >
      <div className="space-y-3">
        {incomplete && (
          <div className="flex items-start gap-2.5 rounded-control border border-attention/25 bg-attention-soft px-3 py-2.5">
            <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-attention" />
            <p className="text-[13px] leading-relaxed text-attention-ink">
              Some required details are still missing. The city will refuse the
              submission — finish the application first.
            </p>
          </div>
        )}

        {triggersFire && (
          <div className="flex items-start gap-2.5 rounded-control border border-line bg-surface-muted px-3 py-2.5">
            <Flame aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-500" />
            <p className="text-[13px] leading-relaxed text-ink-600">
              Attendance of {formatNumber(application.expected_attendance)} is above
              5,000, so the fire department is added to the review automatically.
            </p>
          </div>
        )}

        {submit.error && <InlineError error={submit.error} />}
      </div>
    </ConfirmDialog>
  );
}

/**
 * Resubmit confirmation.
 *
 * The consequence worth stating is not "are you sure" but *who will be asked
 * again*: only agencies that requested changes go back to Pending, and approvals
 * already given are preserved. Saying so prevents the most damaging mistake here,
 * which is resubmitting and assuming an earlier approval has been withdrawn.
 */
function ResubmitDialog({
  open,
  onOpenChange,
  applicationId,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  applicationId: string;
  onDone: (result: ResubmitApplicationResponse) => void;
}) {
  const token = useToken();

  const resubmit = useMutation(() => resubmitApplication(applicationId, { token }));

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Resubmit for review?"
      confirmLabel="Resubmit"
      tone="primary"
      loading={resubmit.isPending}
      onConfirm={async () => {
        const result = await resubmit.run();
        if (result) onDone(result);
      }}
      description={
        <>
          Agencies that requested changes will be asked to review the application
          again. Agencies that have already approved keep their approval and are not
          asked twice.
        </>
      }
    >
      {resubmit.error && <InlineError error={resubmit.error} />}
    </ConfirmDialog>
  );
}

/* --- Skeleton ------------------------------------------------------------- */

function DetailSkeleton() {
  return (
    <>
      <PageHeader title="Loading application…" />
      <PageBody>
        <div className="space-y-5">
          <div className="flex gap-2">
            <Skeleton className="h-6 w-28 rounded-full" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
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
        </div>
      </PageBody>
    </>
  );
}