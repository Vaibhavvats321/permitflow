/**
 * Business rules the frontend mirrors from the backend.
 *
 * Each of these has a server-side counterpart in `app.core.routing`, and each
 * carries the threshold's direction with it — `> 5000`, not `>= 5000`, because
 * the brief says "over 5,000" and the copy in the form has to match the copy the
 * server acts on.
 */

/** Attendance above which the fire department is added to the review. */
export const LARGE_EVENT_THRESHOLD = 5000;

/** The server's default and maximum page size for both list endpoints. */
export const PAGE_SIZE = 50;

/**
 * A page size chosen to be visibly smaller than the server's cap of 50.
 *
 * The list endpoints return a bare array with no total count, so "load more" is
 * the only honest pagination. Asking for fewer rows per request makes the
 * incremental behaviour obvious instead of leaving a user wondering whether a
 * screen showing 50 rows is the whole dataset.
 */
export const PageSize = 20;