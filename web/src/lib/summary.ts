import type { ApplicationResponse } from "./types";

/**
 * Derive an organizer's dashboard from the applications they own.
 *
 * Computed client-side over a single list request rather than by adding a
 * stats endpoint. Two reasons: the numbers are all derivable from data the
 * dashboard already needs, and inventing a server endpoint for arithmetic the
 * browser can do would be backend scope creep for a presentation concern.
 *
 * The trade-off is honest and documented — this summarises the loaded page, not
 * every application the organizer may have. Anything presented as a total says so.
 */

/** The fields the dashboard groups by. Kept narrow for the same reason. */
type SlimApplication = Pick<
  ApplicationResponse,
  | "id"
  | "status"
  | "event_name"
  | "event_type"
  | "start_date"
  | "end_date"
  | "updated_at"
  | "reviews"
>;

export interface DashboardSummary {
  /** Applications in the loaded set, by status. */
  counts: Record<ApplicationResponse["status"], number>;
  /** Needs the organizer's attention right now. */
  needsAction: SlimApplication[];
  /** In flight with agencies. */
  inFlight: SlimApplication[];
  /** Awaiting a first decision, longest outstanding first. */
  awaitingDecision: SlimApplication[];
  /** Recently touched, for an "activity" strip. */
  recent: SlimApplication[];
  /** Applications carrying at least one agency comment. */
  withFeedback: number;
  /** Mean agencies per submitted application. Null when nothing is submitted. */
  averageAgencies: number | null;
  /** Applications with no reviews assigned yet. */
  unsubmitted: number;
}

const STATUS_KEYS: ApplicationResponse["status"][] = [
  "Draft",
  "Submitted",
  "Under Review",
  "Approved",
  "Rejected",
  "Changes Requested",
];

export function summarize(applications: ApplicationResponse[]): DashboardSummary {
  const counts = Object.fromEntries(
    STATUS_KEYS.map((status) => [status, 0]),
  ) as DashboardSummary["counts"];

  for (const application of applications) {
    counts[application.status] += 1;
  }

  // Reorder the keys so a record literal satisfies `DashboardSummary["counts"]`
  // exactly — the two lists must not drift apart.
  const orderedCounts = Object.fromEntries(
    STATUS_KEYS.map((status) => [status, counts[status]]),
  ) as DashboardSummary["counts"];

  const byRecency = (a: SlimApplication, b: SlimApplication) =>
    new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();

  const submitted = applications.filter((a) => a.status !== "Draft");

  const reviewCounts = submitted.map((a) => a.reviews.length);
  const averageAgencies =
    reviewCounts.length > 0
      ? reviewCounts.reduce((total, count) => total + count, 0) / reviewCounts.length
      : null;

  return {
    counts: orderedCounts,
    // "Needs action" is the set of applications the API will accept an edit on:
    // drafts and those an agency sent back. Anything else is either waiting on an
    // agency or settled, and surfacing those as actionable would train people to
    // ignore the section.
    needsAction: applications
      .filter((a) => a.status === "Draft" || a.status === "Changes Requested")
      .sort(byRecency)
      .slice(0, 5),
    inFlight: applications
      .filter((a) => a.status === "Submitted" || a.status === "Under Review")
      .sort(byRecency),
    awaitingDecision: applications
      .filter((a) => a.reviews.some((review) => review.review_status === "Pending"))
      .sort((a, b) => {
        const aPending = oldestPending(a);
        const bPending = oldestPending(b);
        return aPending - bPending;
      })
      .slice(0, 5),
    recent: [...applications].sort(byRecency).slice(0, 6),
    withFeedback: applications.filter((a) =>
      a.reviews.some((review) => review.comment && review.comment.trim().length > 0),
    ).length,
    averageAgencies,
    unsubmitted: counts.Draft,
  };
}

/**
 * The earliest `created_at` among a task's Pending reviews.
 *
 * Used to rank by how long a decision has been outstanding, which is the question
 * "what is stuck" actually means. Returns 0 for an application with no Pending
 * tasks so it sorts last rather than first.
 */
function oldestPending(application: SlimApplication): number {
  const timestamps = application.reviews
    .filter((review) => review.review_status === "Pending")
    .map((review) => new Date(review.created_at).getTime());

  if (timestamps.length === 0) return Number.MAX_SAFE_INTEGER;
  return Math.min(...timestamps);
}

/** Days since an application was last touched, floored at 0. */
export function daysSince(iso: string): number {
  const elapsed = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(elapsed / 86_400_000));
}

/** How long a decision has been outstanding, in whole days. */
export function daysPending(application: SlimApplication): number {
  const oldest = oldestPending(application);
  if (oldest === Number.MAX_SAFE_INTEGER) return 0;
  return Math.max(0, Math.floor((Date.now() - oldest) / 86_400_000));
}