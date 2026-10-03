"use client";

import {
  ArrowRight,
  MapPin,
  Plus,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { useToken } from "@/lib/auth";
import { listApplications } from "@/lib/endpoints";
import {
  formatDateRange,
  formatRelative,
  truncate,
} from "@/lib/format";
import { applicationStatus } from "@/lib/status";
import {
  APPLICATION_STATUSES,
  EVENT_TYPES,
  type ApplicationResponse,
  type ApplicationStatus,
  type EventType,
} from "@/lib/types";
import { PageSize } from "@/lib/constants";
import { usePaginatedApi } from "@/lib/use-api";
import { Badge, CountChip, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/card";
import {
  ErrorState,
  NoApplicationsEmptyState,
  NoMatchingFiltersEmptyState,
} from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonRows } from "@/components/ui/skeleton";
import {
  SortableHeadCell,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeadCell,
  TableRow,
  FilterField,
  useQueryParamState,
} from "@/components/ui/table";
import {
  ReviewProgressBar,
  ReviewProgressLegend,
  countReviewStates,
} from "@/components/applications/stat-cards";

/**
 * The organizer's application list.
 *
 * Three filter controls and a client-side text search, then sorting. Pagination
 * is "load more" because the endpoint returns a bare array with no total — the
 * UI cannot state "page 2 of 7" without inventing that number, so it accumulates
 * and says how many rows are currently loaded.
 *
 * The search box filters the loaded set only, and says so in its hint. It is
 * honest about being a convenience over what is on screen rather than pretending
 * to be a server-side index.
 */

const ALL = "__all__";

type SortKey = "event_name" | "status" | "start_date" | "updated_at";

export function ApplicationsList() {
  const token = useToken();

  // Filters live in the URL so the view is shareable and the back button steps
  // back through filter changes rather than leaving the page.
  const [statusParam, setStatusParam] = useQueryParamState("status", ALL);
  const [eventTypeParam, setEventTypeParam] = useQueryParamState("event_type", ALL);
  const [query, setQuery] = useState("");

  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "updated_at",
    direction: "desc",
  });

  const status = statusParam === ALL ? undefined : (statusParam as ApplicationStatus);
  const eventType = eventTypeParam === ALL ? undefined : (eventTypeParam as EventType);

  const hasFilters = status !== undefined || eventType !== undefined || query !== "";

  function clearFilters() {
    setStatusParam(ALL);
    setEventTypeParam(ALL);
    setQuery("");
  }

  // Pages accumulate: "load more" appends to what is already on screen instead of
  // replacing it, so the row a user is looking at does not vanish underneath them.
  // Filters are part of the cache key, so changing one restarts from the first page
  // rather than appending rows from a different result set.
  const {
    items: applications,
    error,
    isLoading,
    isRefreshing,
    isLoadingMore,
    mayHaveMore,
    loadMore,
    reload,
  } = usePaginatedApi<ApplicationResponse>(
    useCallback(
      (signal, offset, limit) =>
        listApplications({ status, event_type: eventType, offset, limit }, { token, signal }),
      [token, status, eventType],
    ),
    PageSize,
    [token, status, eventType],
    (application) => application.id,
  );

  function onStatusChange(next: string) {
    setStatusParam(next);
  }

  function onEventTypeChange(next: string) {
    setEventTypeParam(next);
  }

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered =
      needle === ""
        ? applications
        : applications.filter((application) =>
            [application.event_name, application.location ?? "", application.description ?? ""]
              .join(" ")
              .toLowerCase()
              .includes(needle),
          );

    const direction = sort.direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      switch (sort.key) {
        case "event_name":
          return a.event_name.localeCompare(b.event_name) * direction;
        case "status":
          return a.status.localeCompare(b.status) * direction;
        case "start_date":
          // Null dates sort last in both directions: an application with no date
          // yet is not "earliest" just because it is empty.
          return compareNullable(a.start_date, b.start_date) * direction;
        case "updated_at":
          return (
            (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()) * direction
          );
      }
    });
  }, [applications, query, sort]);

  const counts = useMemo(
    () => summarizeCounts(applications),
    [applications],
  );

  function onSort(key: string) {
    setSort((current) =>
      current.key === key
        ? { key: key as SortKey, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key: key as SortKey, direction: key === "event_name" ? "asc" : "desc" },
    );
  }

  /* --- Render ------------------------------------------------------------- */

  if (error) {
    return (
      <Panel bodyClassName="p-0">
        <ErrorState error={error} onRetry={reload} />
      </Panel>
    );
  }

  const isFirstLoad = isLoading;

  return (
    <Panel bodyClassName="p-0">
      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3 border-b border-line p-4">
        <div className="min-w-[13rem] flex-1">
          <label
            htmlFor="application-search"
            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-ink-500"
          >
            Search loaded applications
          </label>
          <Input
            id="application-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name, location or description"
            leading={<Search />}
            disabled={isFirstLoad}
          />
        </div>

        <FilterField label="Status" htmlFor="filter-status" className="w-44">
          <Select value={statusParam} onValueChange={onStatusChange} disabled={isFirstLoad}>
            <SelectTrigger id="filter-status" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All statuses</SelectItem>
              {APPLICATION_STATUSES.map((value) => (
                <SelectItem key={value} value={value}>
                  {applicationStatus(value).label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>

        <FilterField label="Event type" htmlFor="filter-event-type" className="w-44">
          <Select value={eventTypeParam} onValueChange={onEventTypeChange} disabled={isFirstLoad}>
            <SelectTrigger id="filter-event-type" aria-label="Filter by event type">
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

      {/* Loaded-count bar. States the number rather than implying it is a total. */}
      {!isFirstLoad && applications.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface-muted px-4 py-2.5">
          <p className="text-[13px] text-ink-500">
            Showing <span className="tabular font-medium text-ink-800">{visible.length}</span>{" "}
            of <span className="tabular font-medium text-ink-800">{applications.length}</span>{" "}
            loaded
            {mayHaveMore && " · more available"}
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {(["Draft", "Submitted", "Under Review", "Approved", "Rejected", "Changes Requested"] as const)
              .filter((value) => counts[value] > 0)
              .map((value) => {
                const presentation = applicationStatus(value);
                return (
                  <Badge key={value} tone={presentation.tone} size="sm" dot={false}>
                    {presentation.label}
                    <CountChip value={counts[value]} className="ml-0.5 bg-white/70 text-ink-600" />
                  </Badge>
                );
              })}
          </div>

          {isRefreshing && <p className="text-[13px] text-ink-400">Refreshing…</p>}
        </div>
      )}

      {/* Body */}
      {isFirstLoad ? (
        <SkeletonRows rows={6} columns={5} />
      ) : applications.length === 0 ? (
        hasFilters ? (
          <NoMatchingFiltersEmptyState onClear={clearFilters} />
        ) : (
          <NoApplicationsEmptyState
            action={
              <Button asChild variant="primary" size="sm">
                <Link href="/applications/new">
                  <Plus aria-hidden />
                  New application
                </Link>
              </Button>
            }
          />
        )
      ) : visible.length === 0 ? (
        <NoMatchingFiltersEmptyState onClear={clearFilters} />
      ) : (
        <>
          <ApplicationTable
            applications={visible}
            sort={sort}
            onSort={onSort}
            queryActive={query.trim() !== ""}
          />

          {/* "Load more" is a full-width row rather than a floating button, so
              it reads as part of the list and is reachable without scrolling. */}
          {mayHaveMore && (
            <div className="flex flex-col items-center gap-2 border-t border-line p-4">
              <Button
                variant="default"
                icon={<RotateCcw />}
                loading={isLoadingMore}
                onClick={loadMore}
              >
                Load more applications
              </Button>
              <p className="text-[12px] text-ink-400">
                {applications.length} loaded so far
              </p>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

/* --- Table ---------------------------------------------------------------- */

function ApplicationTable({
  applications,
  sort,
  onSort,
  queryActive,
}: {
  applications: ApplicationResponse[];
  sort: { key: SortKey; direction: "asc" | "desc" };
  onSort: (key: string) => void;
  queryActive: boolean;
}) {
  return (
    <>
      {/* Table from `md` up. */}
      <div className="hidden md:block">
        <Table>
          <caption className="sr-only">
            Your permit applications{queryActive ? ", filtered by search" : ""},{" "}
            {applications.length} shown
          </caption>
          <TableHead>
            <TableRow className="hover:bg-transparent">
              <SortableHeadCell label="Event" sortKey="event_name" sort={sort} onSort={onSort} />
              <TableHeadCell>Status</TableHeadCell>
              <TableHeadCell>Agency progress</TableHeadCell>
              <SortableHeadCell
                label="Event dates"
                sortKey="start_date"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeadCell
                label="Updated"
                sortKey="updated_at"
                sort={sort}
                onSort={onSort}
              />
              <TableHeadCell className="w-10">
                <span className="sr-only">Open</span>
              </TableHeadCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {applications.map((application) => {
              const presentation = applicationStatus(application.status);
              const { approved, pending, blocked } = countReviewStates(application.reviews);

              return (
                <TableRow key={application.id} className="group">
                  <TableCell>
                    <Link
                      href={`/applications/${application.id}`}
                      className="block focus-visible:outline-none"
                    >
                      <span className="block max-w-[16rem] truncate text-[13px] font-medium text-ink-900 transition-colors group-hover:text-brand-700">
                        {application.event_name}
                      </span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-500">
                        {application.event_type}
                        {application.location && (
                          <>
                            <span aria-hidden>·</span>
                            <span className="inline-flex min-w-0 items-center gap-1">
                              <MapPin aria-hidden className="size-3 shrink-0" />
                              <span className="truncate">
                                {truncate(application.location, 40)}
                              </span>
                            </span>
                          </>
                        )}
                      </span>
                    </Link>
                  </TableCell>

                  <TableCell>
                    <StatusBadge presentation={presentation} size="sm" />
                  </TableCell>

                  <TableCell className="w-56">
                    {application.reviews.length > 0 ? (
                      <div className="space-y-1.5">
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
                    ) : (
                      <span className="text-[13px] text-ink-400">
                        {application.status === "Draft"
                          ? "Not sent to any agency"
                          : "No agencies assigned"}
                      </span>
                    )}
                  </TableCell>

                  <TableCell>
                    <span className="tabular whitespace-nowrap text-[13px] text-ink-600">
                      {formatDateRange(application.start_date, application.end_date)}
                    </span>
                  </TableCell>

                  <TableCell>
                    <span className="whitespace-nowrap text-[13px] text-ink-500">
                      {formatRelative(application.updated_at)}
                    </span>
                  </TableCell>

                  <TableCell>
                    <Button
                      asChild
                      variant="ghost"
                      size="icon-sm"
                      className="text-ink-400 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <Link href={`/applications/${application.id}`}>
                        <ArrowRight aria-hidden />
                        <span className="sr-only">Open {application.event_name}</span>
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Cards below `md`. The same data, laid out for a narrow viewport. */}
      <ul className="divide-y divide-line md:hidden">
        {applications.map((application) => {
          const presentation = applicationStatus(application.status);
          const { approved, pending, blocked } = countReviewStates(application.reviews);

          return (
            <li key={application.id}>
              <Link
                href={`/applications/${application.id}`}
                className="block px-4 py-4 transition-colors active:bg-surface-muted"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink-900">
                      {application.event_name}
                    </p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-500">
                      <span>{application.event_type}</span>
                      <span aria-hidden>·</span>
                      <span className="tabular">
                        {formatDateRange(application.start_date, application.end_date)}
                      </span>
                    </p>
                  </div>
                  <StatusBadge presentation={presentation} size="sm" dot={false} />
                </div>

                {application.reviews.length > 0 ? (
                  <div className="mt-3 space-y-1.5">
                    <ReviewProgressBar
                      total={application.reviews.length}
                      approved={approved}
                      pending={pending}
                      blocked={blocked}
                    />
                    <ReviewProgressLegend approved={approved} pending={pending} blocked={blocked} />
                  </div>
                ) : (
                  <p className="mt-3 text-[12px] text-ink-400">Not sent to any agency</p>
                )}

                <p className="mt-3 text-[12px] text-ink-400">
                  Updated {formatRelative(application.updated_at)}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/* --- Helpers -------------------------------------------------------------- */

/** Count statuses across the loaded set, for the summary chips. */
function summarizeCounts(applications: ApplicationResponse[]) {
  const counts = Object.fromEntries(
    APPLICATION_STATUSES.map((status) => [status, 0]),
  ) as Record<ApplicationStatus, number>;

  for (const application of applications) {
    counts[application.status] += 1;
  }
  return counts;
}

/**
 * Compare two nullable timestamps.
 *
 * `null` sorts last regardless of direction, because an application with no date
 * set is not meaningfully "earliest" or "latest".
 */
function compareNullable(a: string | null, b: string | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return new Date(a).getTime() - new Date(b).getTime();
}