/**
 * Shared frontend constants.
 *
 * Attendance thresholds deliberately live in the database, not here: each
 * agency carries its own value, served by GET /agencies and mirrored for UI
 * copy by `lib/routing.ts`. Nothing in the frontend hardcodes a limit.
 */

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