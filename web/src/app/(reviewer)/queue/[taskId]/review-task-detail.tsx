"use client";

import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock,
  Flame,
  Info,
  MapPin,
  MessageSquare,
  RotateCcw,
  Users,
  XCircle,
} from "lucide-react";
import { useCallback, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import {
  getReviewHistory,
  getReviewTask,
  submitReviewDecision,
} from "@/lib/endpoints";
import {
  formatDate,
  formatDateTime,
  formatNumber,
  formatRelative,
} from "@/lib/format";
import { applicationStatus, reviewStatus } from "@/lib/status";
import type {
  ApplicationHistoryResponse,
  ReviewAction,
  ReviewTaskResponse,
} from "@/lib/types";
import { useApi, useMutation } from "@/lib/use-api";
import { cn } from "@/lib/cn";
import { LARGE_EVENT_THRESHOLD } from "@/lib/constants";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, DetailList, DetailRow, Panel } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { ErrorState, InlineError } from "@/components/ui/empty-state";
import { Field, Textarea } from "@/components/ui/input";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { HistoryTimeline } from "@/components/applications/history-timeline";

/**
 * A single review task.
 *
 * Reviewers get exactly one write operation — a decision plus a comment. There is
 * no edit of application fields on this screen, and that is enforced by the API
 * rather than by hiding buttons: `ReviewActionRequest` has `extra="forbid"`, so a
 * request trying to change the event's dates is a 422, not a silent no-op.
 *
 * The decision panel is a dialog rather than an inline form so that reading an
 * application and acting on it stay visually separate. It also means a reviewer
 * cannot submit a comment they have not actually finished writing, because the
 * only way to send a decision is a deliberate, named button.
 */

/** Placeholder text per action: what the server expects this to contain. */
const COMMENT_HINT: Record<ReviewAction, string> = {
  approve:
    "Required even for approval — this is the only record of your assessment the organizer will have.",
  request_changes:
    "Be specific about what needs changing. The organizer sees this verbatim and cannot see your notes.",
  reject:
    "Explain why this cannot be permitted. This closes the application; it cannot be resubmitted.",
};

/** Max length enforced by the server's `max_length=2000`. */
const COMMENT_MAX = 2000;

const ACTION_META: Record<
  ReviewAction,
  { label: string; title: string; confirmLabel: string; icon: typeof CheckCircle2; iconClass: string }
> = {
  approve: {
    label: "Approve",
    title: "Approve this application?",
    confirmLabel: "Approve",
    icon: CheckCircle2,
    iconClass: "bg-positive-soft text-positive",
  },
  request_changes: {
    label: "Request changes",
    title: "Request changes?",
    confirmLabel: "Request changes",
    icon: RotateCcw,
    iconClass: "bg-attention-soft text-attention",
  },
  reject: {
    label: "Reject",
    title: "Reject this application?",
    confirmLabel: "Reject application",
    icon: XCircle,
    iconClass: "bg-critical-soft text-critical",
  },
};

export function ReviewTaskDetail() {
  const token = useToken();
  const toast = useToast();
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId;

  const [pendingAction, setPendingAction] = useState<ReviewAction | null>(null);
  const [comment, setComment] = useState("");
  const [commentError, setCommentError] = useState<string>();

  const task = useApi<ReviewTaskResponse>(
    useCallback((signal) => getReviewTask(taskId, { token, signal }), [token, taskId]),
    [token, taskId],
  );

  const decide = useMutation((action: ReviewAction, text: string) =>
    submitReviewDecision(taskId, action, text, { token }),
  );

  const { data, error, isLoading, reload, setData } = task;

  if (isLoading) return <TaskSkeleton />;

  if (error) {
    return (
      <>
        <PageHeader
          title="Review task"
          crumbs={[{ label: "Review queue", href: "/queue" }, { label: "Unavailable" }]}
        />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader title="Review task" />
        <PageBody>
          <ErrorState
            error={new ApiError(0, "The task could not be loaded.")}
            onRetry={reload}
          />
        </PageBody>
      </>
    );
  }

  const own = reviewStatus(data.review_status);
  const overall = applicationStatus(data.application.status);
  const isRejectedOverall = data.application.status === "Rejected";
  const isActionable = data.review_status === "Pending" && !isRejectedOverall;
  const hasComment = Boolean(data.comment?.trim());
  const isLargeEvent = (data.application.expected_attendance ?? 0) > LARGE_EVENT_THRESHOLD;
  const currentStatus = data.application.status;

  async function confirmDecision() {
    if (!pendingAction) return;

    const trimmed = comment.trim();
    if (trimmed === "") {
      setCommentError("A comment is required for every decision.");
      return;
    }
    if (trimmed.length > COMMENT_MAX) {
      setCommentError(`Keep the comment to ${COMMENT_MAX} characters or fewer.`);
      return;
    }

    const result = await decide.run(pendingAction, trimmed);
    if (!result) return;

    setPendingAction(null);
    setComment("");
    setCommentError(undefined);
    // The response carries the updated task and the resulting application status,
    // so the page updates without a refetch that would discard scroll position.
    setData(result.task);
    toast.success(
      `Decision recorded: ${ACTION_META[pendingAction].label.toLowerCase()}`,
      result.application_status === currentStatus
        ? "Other agencies are still to decide."
        : `Overall status is now ${applicationStatus(result.application_status).label}.`,
    );
  }

  return (
    <>
      <PageHeader
        title={data.application.event_name}
        crumbs={[
          { label: "Review queue", href: "/queue" },
          { label: data.application.event_name },
        ]}
        actions={
          isActionable ? (
            <Button variant="primary" icon={<MessageSquare />} onClick={() => setPendingAction("approve")}>
              Record a decision
            </Button>
          ) : undefined
        }
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="flex items-center gap-1.5">
            <span className="text-[13px] text-ink-500">Your decision:</span>
            <StatusBadge presentation={own} size="sm" />
          </span>
          <span className="flex items-center gap-1.5">
            <span className="text-[13px] text-ink-500">Overall:</span>
            <StatusBadge presentation={overall} size="sm" dot={false} />
          </span>
          <span aria-hidden className="text-ink-300">
            ·
          </span>
          <span className="text-[13px] text-ink-500">
            Assigned {formatRelative(data.created_at)}
          </span>
        </div>
      </PageHeader>

      <PageBody>
        {/* The decision prompt, always visible above the tabs. A reviewer arriving
            from the queue needs to know what is being asked of them before reading
            the detail. */}
        {isActionable ? (
          <div className="mb-6 rounded-card border border-brand-200 bg-brand-50/50 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-control bg-white/80 text-brand-600">
                  <MessageSquare aria-hidden className="size-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-ink-900">
                    Your agency&rsquo;s assessment is required
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink-600">
                    Every decision needs a written comment. The organizer sees it
                    verbatim and cannot see your internal notes.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="default"
                  icon={<RotateCcw />}
                  onClick={() => setPendingAction("request_changes")}
                >
                  Request changes
                </Button>
                <Button
                  variant="danger"
                  icon={<XCircle />}
                  onClick={() => setPendingAction("reject")}
                >
                  Reject
                </Button>
                <Button
                  variant="primary"
                  icon={<CheckCircle2 />}
                  onClick={() => setPendingAction("approve")}
                >
                  Approve
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="mb-6 rounded-card border border-line bg-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-control border border-line bg-surface-muted text-ink-500">
                  {data.review_status === "Approved" ? (
                    <CheckCircle2 aria-hidden className="size-4" />
                  ) : (
                    <Clock aria-hidden className="size-4" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-ink-900">
                    {data.review_status === "Pending"
                      ? isRejectedOverall
                        ? "No decision is needed from your agency"
                        : "Still awaiting your decision"
                      : `You recorded "${own.label}" ${formatRelative(data.updated_at)}`}
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink-600">
                    {data.review_status === "Pending"
                      ? isRejectedOverall
                        ? "Another agency already rejected this application, so the outcome is final. You can read the details and history below, but no review actions are available."
                        : "This task is still open for your agency."
                      : isRejectedOverall
                        ? "Another agency rejected this application, so the outcome is final and no further decisions can be recorded."
                        : "A reviewer may record a new decision, which replaces the previous one and is added to the history."}
                  </p>
                </div>
              </div>
              {data.review_status !== "Pending" && !isRejectedOverall && (
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => setPendingAction(data.review_status === "Approved" ? "request_changes" : "approve")}
                >
                  Record a different decision
                </Button>
              )}
            </div>

            {hasComment && (
              <>
                <Separator className="my-4" />
                <p className="text-[12px] font-medium uppercase tracking-wide text-ink-400">
                  Your comment
                </p>
                <blockquote
                  className={cn(
                    "mt-2 rounded-control border-l-2 bg-surface-muted px-3.5 py-2.5",
                    "text-[13px] leading-relaxed text-ink-700",
                    data.review_status === "Rejected"
                      ? "border-critical/40"
                      : data.review_status === "Changes Requested"
                        ? "border-attention/40"
                        : "border-positive/40",
                  )}
                >
                  {data.comment}
                </blockquote>
              </>
            )}
          </div>
        )}

        <Tabs defaultValue="application">
          <TabsList className="mb-6">
            <TabsTrigger value="application">Application</TabsTrigger>
            <TabsTrigger value="history">Decision history</TabsTrigger>
          </TabsList>

          <TabsContent value="application">
            <div className="grid gap-5 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <Panel title="Event details" bodyClassName="px-5 pb-2 pt-1">
                  <DetailList>
                    <DetailRow label="Event name">{data.application.event_name}</DetailRow>
                    <DetailRow label="Event type">{data.application.event_type}</DetailRow>
                    <DetailRow label="Dates">
                      {formatDate(data.application.start_date)} →{" "}
                      {formatDate(data.application.end_date)}
                      {data.application.start_date && (
                        <span className="tabular mt-0.5 block text-[13px] text-ink-500">
                          {new Date(data.application.start_date).toLocaleTimeString(undefined, {
                            hour: "numeric",
                            minute: "2-digit",
                          })}
                          {" – "}
                          {data.application.end_date &&
                            new Date(data.application.end_date).toLocaleTimeString(undefined, {
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                        </span>
                      )}
                    </DetailRow>
                    <DetailRow label="Location">
                      {data.application.location ? (
                        <span className="inline-flex items-center gap-1.5">
                          <MapPin aria-hidden className="size-3.5 text-ink-400" />
                          {data.application.location}
                        </span>
                      ) : (
                        <span className="text-ink-400">Not set</span>
                      )}
                    </DetailRow>
                    <DetailRow label="Expected attendance">
                      {data.application.expected_attendance !== null ? (
                        <>
                          <span className="tabular inline-flex items-center gap-1.5">
                            <Users aria-hidden className="size-3.5 text-ink-400" />
                            {formatNumber(data.application.expected_attendance)} people
                          </span>
                          {isLargeEvent && (
                            <span className="mt-1.5 flex items-center gap-1.5 text-[13px] text-attention-ink">
                              <Flame aria-hidden className="size-3.5 shrink-0" />
                              Above {LARGE_EVENT_THRESHOLD.toLocaleString()}, so a fire
                              review was added to this application
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-ink-400">Not set</span>
                      )}
                    </DetailRow>
                    <DetailRow label="Description">
                      {data.application.description ? (
                        <p className="whitespace-pre-line leading-relaxed">
                          {data.application.description}
                        </p>
                      ) : (
                        <span className="text-ink-400">
                          The organizer provided no description
                        </span>
                      )}
                    </DetailRow>
                    <DetailRow label="Submitted">
                      {formatDateTime(data.created_at)}
                    </DetailRow>
                  </DetailList>
                </Panel>
              </div>

              <div className="space-y-5">
                {/* Overall status explained. A reviewer needs to know whether their
                    colleagues have already objected before deciding. */}
                <Card>
                  <p className="text-[12px] font-medium uppercase tracking-wide text-ink-400">
                    Overall application status
                  </p>
                  <div className="mt-2.5">
                    <StatusBadge presentation={overall} />
                  </div>
                  <p className="mt-3 text-[13px] leading-relaxed text-ink-600">
                    {overall.description}
                  </p>

                  {isRejectedOverall && data.review_status !== "Rejected" && (
                      <div className="mt-4 flex items-start gap-2.5 rounded-control border border-critical/20 bg-critical-soft px-3 py-2.5">
                        <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0 text-critical" />
                        <p className="text-[13px] leading-relaxed text-critical-ink">
                          Another agency has rejected this application, so the
                          outcome is final. This page is read-only — no further
                          review decisions can be recorded.
                        </p>
                      </div>
                    )}
                </Card>

                <Card>
                  <p className="text-[12px] font-medium uppercase tracking-wide text-ink-400">
                    What your comment is used for
                  </p>
                  <ul className="mt-3 space-y-2.5 text-[13px] leading-relaxed text-ink-600">
                    <li className="flex gap-2">
                      <Info aria-hidden className="mt-0.5 size-3.5 shrink-0 text-ink-400" />
                      It is shown to the organizer verbatim, alongside which agency
                      wrote it.
                    </li>
                    <li className="flex gap-2">
                      <CalendarDays aria-hidden className="mt-0.5 size-3.5 shrink-0 text-ink-400" />
                      It is recorded permanently in the application&rsquo;s history,
                      with a timestamp.
                    </li>
                    <li className="flex gap-2">
                      <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0 text-ink-400" />
                      There is no private note field — assume the organizer will read
                      it.
                    </li>
                  </ul>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="history">
            <TaskHistory token={token} taskId={data.id} />
          </TabsContent>
        </Tabs>
      </PageBody>

      {/* --- Decision dialog ---------------------------------------------- */}

      <Dialog
        open={pendingAction !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingAction(null);
            setCommentError(undefined);
            decide.reset();
          }
        }}
      >
        {pendingAction && (
          <DecisionDialogBody
            action={pendingAction}
            comment={comment}
            onCommentChange={(value) => {
              setComment(value);
              if (commentError) setCommentError(undefined);
            }}
            error={commentError}
            serverError={decide.error}
            isPending={decide.isPending}
            eventName={data.application.event_name}
            onConfirm={confirmDecision}
          />
        )}
      </Dialog>
    </>
  );
}

/* --- Dialog body ---------------------------------------------------------- */

/**
 * The dialog's contents, split out so the decision dialog's markup is a single
 * readable unit rather than being buried inside the detail component.
 */
function DecisionDialogBody({
  action,
  comment,
  onCommentChange,
  error,
  serverError,
  isPending,
  eventName,
  onConfirm,
}: {
  action: ReviewAction;
  comment: string;
  onCommentChange: (value: string) => void;
  error?: string;
  serverError?: ApiError;
  isPending: boolean;
  eventName: string;
  onConfirm: () => void;
}) {
  const meta = ACTION_META[action];
  const Icon = meta.icon;
  const remaining = COMMENT_MAX - comment.length;

  return (
    <DialogContent hideClose className="p-0">
      <div className="flex flex-col gap-3 p-6 pb-4">
        <span
          className={cn(
            "flex size-10 items-center justify-center rounded-control",
            meta.iconClass,
          )}
        >
          <Icon aria-hidden className="size-5" />
        </span>
        <div>
          <h2 className="text-base font-semibold tracking-tight text-ink-900">
            {meta.title}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-600">
            {action === "approve" && (
              <>
                Your agency approves <span className="font-medium text-ink-800">{eventName}</span>
                . This is recorded permanently and cannot be undone.
              </>
            )}
            {action === "request_changes" && (
              <>
                <span className="font-medium text-ink-800">{eventName}</span> goes back to
                the organizer for correction. They can edit it and resubmit, and your
                agency will be asked again.
              </>
            )}
            {action === "reject" && (
              <>
                <span className="font-medium text-ink-800">{eventName}</span> is declined.
                The application closes and cannot be resubmitted.
              </>
            )}
          </p>
        </div>
      </div>

      <div className="space-y-3 px-6 pb-2">
        <Field
          label="Comment"
          htmlFor="decision-comment"
          required
          error={error ?? serverError?.message}
          hint={
            <>
              {COMMENT_HINT[action]}
              <span className="tabular mt-1 block text-ink-400">
                {remaining} characters remaining
              </span>
            </>
          }
        >
          <Textarea
            id="decision-comment"
            name="comment"
            rows={5}
            value={comment}
            onChange={(event) => onCommentChange(event.target.value)}
            invalid={Boolean(error ?? serverError)}
            maxLength={COMMENT_MAX}
            autoFocus
            placeholder={
              action === "approve"
                ? "The event plan, crowd management and emergency access arrangements meet our requirements."
                : action === "request_changes"
                  ? "Please confirm the barrier layout and provide the stewarding plan for the finish area."
                  : "The proposed route has no viable emergency access for an event of this size."
            }
          />
        </Field>

        {serverError && !serverError.fieldErrors.comment && (
          <InlineError error={serverError} />
        )}
      </div>

      <div className="flex flex-col-reverse gap-2 px-6 py-5 sm:flex-row sm:justify-end">
        {/*
          Cancel closes the dialog rather than running the action, so the two buttons
          at the foot of an irreversible decision dialog cannot be confused.
        */}
        <Button asChild variant="default" disabled={isPending}>
          <DialogClose>Cancel</DialogClose>
        </Button>
        <Button
          variant={action === "reject" ? "danger" : action === "request_changes" ? "default" : "primary"}
          loading={isPending}
          onClick={onConfirm}
        >
          {meta.confirmLabel}
        </Button>
      </div>
    </DialogContent>
  );
}

/* --- History -------------------------------------------------------------- */

function TaskHistory({ token, taskId }: { token: string; taskId: string }) {
  const history = useApi<ApplicationHistoryResponse>(
    useCallback(
      (signal) => getReviewHistory(taskId, { token, signal }),
      [token, taskId],
    ),
    [token, taskId],
  );

  if (history.isLoading) {
    return (
      <Panel>
        <div className="space-y-4">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="flex gap-4">
              <Skeleton className="size-6 shrink-0 rounded-full" />
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

  if (!history.data) return null;

  return <HistoryTimeline history={history.data} viewer="reviewer" />;
}

/* --- Skeleton ------------------------------------------------------------- */

function TaskSkeleton() {
  return (
    <>
      <PageHeader title="Loading review task…" />
      <PageBody>
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <div className="skeleton h-20 rounded-card" />
            <Panel>
              <div className="space-y-5">
                {Array.from({ length: 5 }, (_, index) => (
                  <div key={index} className="space-y-2">
                    <Skeleton className="h-3 w-28" />
                    <Skeleton className="h-3.5 w-2/3" />
                  </div>
                ))}
              </div>
            </Panel>
          </div>
          <Panel>
            <SkeletonText lines={5} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}