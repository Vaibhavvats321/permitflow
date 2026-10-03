"use client";

import { Info, Users } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useToken } from "@/lib/auth";
import { listReviewTasks } from "@/lib/endpoints";
import { formatDateRange, formatNumber, formatRelative, truncate } from "@/lib/format";
import { applicationStatus, reviewStatus } from "@/lib/status";
import {
  EVENT_TYPES,
  type EventType,
  type ReviewStatus,
  type ReviewTaskResponse,
} from "@/lib/types";
import { PageSize } from "@/lib/constants";
import { usePaginatedApi } from "@/lib/use-api";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, Panel } from "@/components/ui/card";
import {
  EmptyQueueFilteredState,
  EmptyQueueState,
  ErrorState,
} from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonCard, SkeletonRows } from "@/components/ui/skeleton";
import {
  FilterField,
  SortableHeadCell,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeadCell,
  TableRow,
  useQueryParamState,
} from "@/components/ui/table";
import {
  ArrowRight,
  CalendarDays,
  MapPin,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { PageBody, PageHeader } from "@/components/layout/page-header";

/**
 * The agency reviewer's queue.
 *
 * Scoped to the signed-in agency by the server, so this is every task assigned to
 * the reviewer — not a slice of it. The headline figure is therefore "awaiting your
 * review" rather than "total", because the actionable subset is the pending one
 * and a queue with nothing pending is a normal, good outcome rather than an empty
 * one worth alarming about.
 *
 * The aggregate application status is shown alongside the reviewer's own decision
 * because "another agency has rejected this" is context a reviewer needs before
 * deciding, and finding it out after submitting is worse than knowing it before.
 */

const ALL = "__all__";

type SortKey = "start_date" | "assigned_at" | "application_status";

export function ReviewQueue() {
  const token = useToken();

  const [statusParam, setStatusParam] = useQueryParamState("status", ALL);
  const [eventTypeParam, setEventTypeParam] = useQueryParamState("event_type", ALL);
  const [query, setQuery] = useState("");

  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "start_date",
    direction: "asc",
  });

  // The reviewer's own decision is a `ReviewStatus`; the filter offers those four,
  // not the six application statuses.
  const status = statusParam === ALL ? undefined : (statusParam as ReviewStatus);
  const eventType = eventTypeParam === ALL ? undefined : (eventTypeParam as EventType);
  const hasFilters = status !== undefined || eventType !== undefined || query !== "";

  function clearFilters() {
    setStatusParam(ALL);
    setEventTypeParam(ALL);
    setQuery("");
  }

  // Pages accumulate, and the filters are part of the cache key, so narrowing to
  // "Pending" restarts from the first page instead of appending to a wider set.
  const {
    items: tasks,
    error,
    isLoading,
    isRefreshing,
    isLoadingMore,
    mayHaveMore,
    loadMore,
    reload,
  } = usePaginatedApi<ReviewTaskResponse>(
    useCallback(
      (signal, offset, limit) =>
        listReviewTasks({ status, event_type: eventType, offset, limit }, { token, signal }),
      [token, status, eventType],
    ),
    PageSize,
    [token, status, eventType],
    (task) => task.id,
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered =
      needle === ""
        ? tasks
        : tasks.filter((task) =>
            [
              task.application.event_name,
              task.application.location ?? "",
              task.application.description ?? "",
            ]
              .join(" ")
              .toLowerCase()
              .includes(needle),
          );

    const direction = sort.direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      switch (sort.key) {
        case "start_date":
          return compareNullable(a.application.start_date, b.application.start_date) * direction;
        case "assigned_at":
          return (
            (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()) * direction
          );
        case "application_status":
          return a.application.status.localeCompare(b.application.status) * direction;
        default:
          return 0;
      }
    });
  }, [tasks, query, sort]);

  const summary = useMemo(() => {
    let pending = 0;
    let decided = 0;
    let changesRequested = 0;
    let rejected = 0;

    for (const task of tasks) {
      switch (task.review_status) {
        case "Pending":
          pending += 1;
          break;
        case "Approved":
          decided += 1;
          break;
        case "Changes Requested":
          changesRequested += 1;
          break;
        case "Rejected":
          rejected += 1;
          break;
      }
    }

    return { pending, decided, changesRequested, rejected, total: tasks.length };
  }, [tasks]);

  function onSort(key: string) {
    setSort((current: { key: SortKey; direction: "asc" | "desc" }) =>
      current.key === key
        ? { key: key as SortKey, direction: current.direction === "asc" ? "desc" : "asc" }
        : // Event dates and assignment age are most useful oldest-first; the
          // overall status reads best alphabetically either way.
          { key: key as SortKey, direction: "asc" },
    );
  }

  if (error) {
    return (
      <>
        <PageHeader
          title="Review queue"
          description="Applications assigned to your agency."
        />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Review queue"
        description="Applications your agency has been asked to assess. Each one needs a decision and a comment."
      >
        {!isLoading && tasks.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="progress" dot>
              {summary.pending} awaiting review
            </Badge>
            {summary.decided > 0 && (
              <Badge tone="positive" dot>
                {summary.decided} approved
              </Badge>
            )}
            {summary.changesRequested > 0 && (
              <Badge tone="attention" dot>
                {summary.changesRequested} requested changes
              </Badge>
            )}
            {summary.rejected > 0 && (
              <Badge tone="critical" dot>
                {summary.rejected} rejected
              </Badge>
            )}
          </div>
        )}
      </PageHeader>

      <PageBody className="space-y-5">
        {isLoading ? (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <SkeletonCard key={index} />
              ))}
            </div>
            <Panel bodyClassName="p-0">
              <SkeletonRows rows={5} columns={4} />
            </Panel>
          </>
        ) : tasks.length === 0 ? (
          <Panel bodyClassName="p-0">
            {hasFilters ? (
              <EmptyQueueFilteredState onClear={clearFilters} />
            ) : (
              <EmptyQueueState />
            )}
          </Panel>
        ) : (
          <>
            <QueueGuidance pending={summary.pending} />

            <Panel bodyClassName="p-0">
              {/* Filters */}
              <div className="flex flex-wrap items-end gap-3 border-b border-line p-4">
                <div className="min-w-[13rem] flex-1">
                  <label
                    htmlFor="queue-search"
                    className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-ink-500"
                  >
                    Search loaded tasks
                  </label>
                  <Input
                    id="queue-search"
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Event, location or description"
                    leading={<Search />}
                  />
                </div>

                <FilterField label="Your decision" htmlFor="queue-status" className="w-44">
                  <Select
                    value={statusParam}
                    onValueChange={(next) => {
                      setStatusParam(next);
                    }}
                  >
                    <SelectTrigger id="queue-status" aria-label="Filter by your decision">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>All decisions</SelectItem>
                      {(["Pending", "Approved", "Changes Requested", "Rejected"] as const).map(
                        (value) => (
                          <SelectItem key={value} value={value}>
                            {reviewStatus(value).label}
                          </SelectItem>
                        ),
                      )}
                    </SelectContent>
                  </Select>
                </FilterField>

                <FilterField label="Event type" htmlFor="queue-event-type" className="w-44">
                  <Select
                    value={eventTypeParam}
                    onValueChange={(next) => {
                      setEventTypeParam(next);
                    }}
                  >
                    <SelectTrigger id="queue-event-type" aria-label="Filter by event type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>All types</SelectItem>
                      {EVENT_TYPES.map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FilterField>

                {hasFilters && (
                  <Button variant="ghost" size="sm" icon={<X />} onClick={clearFilters}>
                    Clear
                  </Button>
                )}
              </div>

              {tasks.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface-muted px-4 py-2.5">
                  <p className="text-[13px] text-ink-500">
                    Showing{" "}
                    <span className="tabular font-medium text-ink-800">{visible.length}</span>{" "}
                    of <span className="tabular font-medium text-ink-800">{tasks.length}</span>{" "}
                    loaded
                    {mayHaveMore && " · more available"}
                  </p>
                  {isRefreshing && <p className="text-[13px] text-ink-400">Refreshing…</p>}
                </div>
              )}

              {visible.length === 0 ? (
                <EmptyQueueFilteredState onClear={clearFilters} />
              ) : (
                <>
                  <QueueTable
                    tasks={visible}
                    sort={sort}
                    onSort={onSort}
                    queryActive={query.trim() !== ""}
                  />

                  {mayHaveMore && (
                    <div className="flex flex-col items-center gap-2 border-t border-line p-4">
                      <Button
                        variant="default"
                        icon={<RotateCcw />}
                        loading={isLoadingMore}
                        onClick={loadMore}
                      >
                        Load more tasks
                      </Button>
                      <p className="text-[12px] text-ink-400">{tasks.length} loaded so far</p>
                    </div>
                  )}
                </>
              )}
            </Panel>
          </>
        )}
      </PageBody>
    </>
  );
}

/* --- Guidance ------------------------------------------------------------- */

/**
 * Explains what a decision obliges the reviewer to do.
 *
 * Worth stating once, at the top of the queue, because the requirement is
 * enforced server-side and a reviewer who does not know it will hit a 422 on
 * their first approve.
 */
function QueueGuidance({ pending }: { pending: number }) {
  return (
    <Card className="border-brand-200 bg-brand-50/40">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-control bg-white/70 text-brand-600">
          <Info aria-hidden className="size-4" />
        </span>
        <div className="min-w-0 text-[13px] leading-relaxed">
          <p className="font-semibold text-ink-900">
            {pending > 0
              ? `${pending} ${pending === 1 ? "application is" : "applications are"} waiting on your agency`
              : "Your queue is up to date"}
          </p>
          <p className="mt-1 text-ink-600">
            Every decision needs a written comment — including approval, which
            becomes the only record the organizer has of your assessment. Requesting
            changes sends the application back to the organizer; rejecting it closes
            the application.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* --- Table ---------------------------------------------------------------- */

function QueueTable({
  tasks,
  sort,
  onSort,
  queryActive,
}: {
  tasks: ReviewTaskResponse[];
  sort: { key: SortKey; direction: "asc" | "desc" };
  onSort: (key: string) => void;
  queryActive: boolean;
}) {
  return (
    <>
      <div className="hidden md:block">
        <Table>
          <caption className="sr-only">
            Applications assigned to your agency{queryActive ? ", filtered by search" : ""},{" "}
            {tasks.length} shown
          </caption>
          <TableHead>
            <TableRow className="hover:bg-transparent">
              <TableHeadCell>Event</TableHeadCell>
              <SortableHeadCell
                label="Event dates"
                sortKey="start_date"
                sort={sort}
                onSort={onSort}
              />
              <TableHeadCell>Your decision</TableHeadCell>
              <SortableHeadCell
                label="Overall status"
                sortKey="application_status"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeadCell
                label="Assigned"
                sortKey="assigned_at"
                sort={sort}
                onSort={onSort}
              />
              <TableHeadCell className="w-10">
                <span className="sr-only">Open</span>
              </TableHeadCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {tasks.map((task) => {
              const own = reviewStatus(task.review_status);
              const overall = applicationStatus(task.application.status);

              return (
                <TableRow key={task.id} className="group">
                  <TableCell>
                    <Link href={`/queue/${task.id}`} className="block">
                      <span className="block max-w-[15rem] truncate text-[13px] font-medium text-ink-900 transition-colors group-hover:text-brand-700">
                        {task.application.event_name}
                      </span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-500">
                        {task.application.event_type}
                        {task.application.location && (
                          <>
                            <span aria-hidden>·</span>
                            <span className="inline-flex min-w-0 items-center gap-1">
                              <MapPin aria-hidden className="size-3 shrink-0" />
                              <span className="truncate">
                                {truncate(task.application.location, 36)}
                              </span>
                            </span>
                          </>
                        )}
                      </span>
                    </Link>
                  </TableCell>

                  <TableCell>
                    <span className="tabular inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-ink-600">
                      <CalendarDays aria-hidden className="size-3.5 text-ink-400" />
                      {formatDateRange(
                        task.application.start_date,
                        task.application.end_date,
                      )}
                    </span>
                    {task.application.expected_attendance !== null && (
                      <span className="tabular mt-0.5 flex items-center gap-1.5 whitespace-nowrap text-[12px] text-ink-400">
                        <Users aria-hidden className="size-3" />
                        {formatNumber(task.application.expected_attendance)} expected
                      </span>
                    )}
                  </TableCell>

                  <TableCell>
                    <StatusBadge presentation={own} size="sm" />
                  </TableCell>

                  <TableCell>
                    <StatusBadge presentation={overall} size="sm" dot={false} />
                    {task.application.status === "Rejected" &&
                      task.review_status !== "Rejected" && (
                        <p className="mt-1 text-[11px] text-critical-ink">
                          Another agency rejected this
                        </p>
                      )}
                  </TableCell>

                  <TableCell>
                    <span className="whitespace-nowrap text-[13px] text-ink-500">
                      {formatRelative(task.created_at)}
                    </span>
                  </TableCell>

                  <TableCell>
                    <Button
                      asChild
                      variant="ghost"
                      size="icon-sm"
                      className="text-ink-400 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <Link href={`/queue/${task.id}`}>
                        <ArrowRight aria-hidden />
                        <span className="sr-only">
                          Review {task.application.event_name}
                        </span>
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ul className="divide-y divide-line md:hidden">
        {tasks.map((task) => {
          const own = reviewStatus(task.review_status);
          const overall = applicationStatus(task.application.status);

          return (
            <li key={task.id}>
              <Link
                href={`/queue/${task.id}`}
                className="block px-4 py-4 transition-colors active:bg-surface-muted"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 flex-1 truncate text-sm font-medium text-ink-900">
                    {task.application.event_name}
                  </p>
                  <StatusBadge presentation={own} size="sm" dot={false} />
                </div>

                <p className="tabular mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-500">
                  <span>{task.application.event_type}</span>
                  <span aria-hidden>·</span>
                  <span>
                    {formatDateRange(
                      task.application.start_date,
                      task.application.end_date,
                    )}
                  </span>
                </p>

                {task.comment && (
                  <p className="mt-2 line-clamp-2 border-l-2 border-line pl-2.5 text-[13px] leading-relaxed text-ink-600">
                    {task.comment}
                  </p>
                )}

                <div className="mt-3 flex items-center justify-between gap-2">
                  <StatusBadge presentation={overall} size="sm" dot={false} />
                  <span className="text-[12px] text-ink-400">
                    {formatRelative(task.created_at)}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/* --- Helpers -------------------------------------------------------------- */

function compareNullable(a: string | null, b: string | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return new Date(a).getTime() - new Date(b).getTime();
}