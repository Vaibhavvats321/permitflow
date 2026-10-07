import type { AgencyResponse } from "./types";

/**
 * Client-side twin of `app.core.routing`'s threshold rule.
 *
 * An agency is required when the expected attendance is *strictly* above its
 * stored threshold — never `>=` — and an agency with no threshold (null) is
 * only ever required by the routing matrix. Values come from the database via
 * GET /agencies, so nothing here hardcodes an agency name or a limit: change
 * Fire's threshold in the admin UI and every hint built on this helper follows.
 *
 * The server re-computes the same rule on submit; this is for showing the
 * requirement before and after submission, not for deciding it.
 */
export function thresholdRequiredAgencies(
  agencies: AgencyResponse[],
  attendance: number | null | undefined,
): AgencyResponse[] {
  if (attendance == null) return [];
  return agencies.filter(
    (agency) =>
      agency.attendance_threshold != null &&
      attendance > agency.attendance_threshold,
  );
}
