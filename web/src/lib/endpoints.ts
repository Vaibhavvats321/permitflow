import { api } from "./api";
import {
  PAGE_SIZE,
  type AdminApplicationHistoryResponse,
  type AdminUserCreate,
  type AdminUserListParams,
  type AdminUserResponse,
  type AdminUserUpdate,
  type AgencyResponse,
  type AgencyWrite,
  type ApplicationHistoryResponse,
  type ApplicationListParams,
  type ApplicationResponse,
  type ApplicationWrite,
  type DashboardSummary,
  type EventType,
  type LoginResponse,
  type ResubmitApplicationResponse,
  type ReviewAction,
  type ReviewActionResponse,
  type ReviewTaskListParams,
  type ReviewTaskResponse,
  type RoutingRule,
  type RoutingRuleCreate,
  type SubmitApplicationResponse,
  type UserResponse,
} from "./types";

/**
 * One function per API operation, with the path and payload shape attached.
 *
 * Screens call these rather than `api.get("/applications?...")`. The query-string
 * encoding lives here, so an event type containing a space can never produce a
 * silently broken filter from a hand-built template string, and the return type
 * travels with the call site instead of being written out twice.
 */

export interface CallOptions {
  token: string;
  signal?: AbortSignal;
}

/**
 * Build a query string, omitting anything unset.
 *
 * `URLSearchParams` is used rather than string concatenation because the values
 * are enum values like `"Under Review"` and `"Street Fair"`, which contain
 * spaces. Interpolated raw they would break the query.
 */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

/* --- Auth ----------------------------------------------------------------- */

export const auth = {
  login(email: string, password: string, signal?: AbortSignal) {
    return api.post<LoginResponse>(
      "/auth/login",
      { email: email.trim(), password },
      { signal },
    );
  },

  me({ token, signal }: CallOptions) {
    return api.get<UserResponse>("/auth/me", { token, signal });
  },
};

/* --- Applications --------------------------------------------------------- */

/**
 * A page of the organizer's applications, newest first.
 *
 * Returns a bare array: the endpoint has no total count, so the caller learns
 * "there may be more" from the array being exactly `limit` long.
 *
 * `q` is passed straight through and matched by the server across every
 * application the caller owns — not just the rows paged into the browser.
 */
export async function listApplications(
  params: ApplicationListParams,
  { token, signal }: CallOptions,
): Promise<ApplicationResponse[]> {
  const search = query({
    q: params.q,
    status: params.status,
    event_type: params.event_type,
    offset: params.offset,
    limit: params.limit ?? PAGE_SIZE,
  });
  return api.get<ApplicationResponse[]>(`/applications${search}`, { token, signal });
}

export function getApplication(id: string, { token, signal }: CallOptions) {
  return api.get<ApplicationResponse>(`/applications/${id}`, { token, signal });
}

export function createApplication(
  payload: ApplicationWrite,
  { token, signal }: CallOptions,
) {
  return api.post<ApplicationResponse>("/applications", payload, { token, signal });
}

/** Full replacement of the editable fields; there is no sparse update. */
export function updateApplication(
  id: string,
  payload: ApplicationWrite,
  { token, signal }: CallOptions,
) {
  return api.put<ApplicationResponse>(`/applications/${id}`, payload, { token, signal });
}

export function submitApplication(
  id: string,
  { token, signal }: CallOptions,
): Promise<SubmitApplicationResponse> {
  return api.post<SubmitApplicationResponse>(
    `/applications/${id}/submit`,
    undefined,
    { token, signal },
  );
}

export function resubmitApplication(
  id: string,
  { token, signal }: CallOptions,
): Promise<ResubmitApplicationResponse> {
  return api.post<ResubmitApplicationResponse>(
    `/applications/${id}/resubmit`,
    undefined,
    { token, signal },
  );
}

export function getApplicationHistory(
  id: string,
  { token, signal }: CallOptions,
): Promise<ApplicationHistoryResponse> {
  return api.get<ApplicationHistoryResponse>(`/applications/${id}/history`, {
    token,
    signal,
  });
}

/* --- Reviews -------------------------------------------------------------- */

/** The signed-in agency's queue. Scoped server-side by `agency_id`. */
export async function listReviewTasks(
  params: ReviewTaskListParams,
  { token, signal }: CallOptions,
): Promise<ReviewTaskResponse[]> {
  const search = query({
    status: params.status,
    event_type: params.event_type,
    offset: params.offset,
    limit: params.limit ?? PAGE_SIZE,
  });
  return api.get<ReviewTaskResponse[]>(`/review-tasks${search}`, { token, signal });
}

export function getReviewTask(id: string, { token, signal }: CallOptions) {
  return api.get<ReviewTaskResponse>(`/review-tasks/${id}`, { token, signal });
}

/**
 * Record a decision. `comment` is required by the server for every action,
 * including approval, so the type makes it mandatory rather than optional with a
 * runtime check buried in the component.
 */
export function submitReviewDecision(
  id: string,
  action: ReviewAction,
  comment: string,
  { token, signal }: CallOptions,
): Promise<ReviewActionResponse> {
  return api.post<ReviewActionResponse>(
    `/review-tasks/${id}/decision`,
    { action, comment },
    { token, signal },
  );
}

export function getReviewHistory(
  id: string,
  { token, signal }: CallOptions,
): Promise<ApplicationHistoryResponse> {
  return api.get<ApplicationHistoryResponse>(`/review-tasks/${id}/history`, {
    token,
    signal,
  });
}

/* --- Admin Dashboard ------------------------------------------------------ */

export function getDashboard({ token, signal }: CallOptions): Promise<DashboardSummary> {
  return api.get<DashboardSummary>("/admin/dashboard", { token, signal });
}

/* --- Admin Applications --------------------------------------------------- */

/**
 * Every application in the admin's city, newest first.
 *
 * Served by the admin-scoped endpoints rather than the organizer ones: the
 * response is the same `ApplicationResponse` shape, but tenant-wide and
 * read-only — there is no create, edit or submit path for this role.
 *
 * `q` is passed straight through to the API, which searches name, location and
 * description in the database. The browser never filters the rows itself, so a
 * match is a match even when the row is still behind "load more".
 */
export async function listAdminApplications(
  params: ApplicationListParams,
  { token, signal }: CallOptions,
): Promise<ApplicationResponse[]> {
  const search = query({
    q: params.q,
    status: params.status,
    event_type: params.event_type,
    offset: params.offset,
    limit: params.limit ?? PAGE_SIZE,
  });
  return api.get<ApplicationResponse[]>(`/admin/applications${search}`, { token, signal });
}

export function getAdminApplication(id: string, { token, signal }: CallOptions) {
  return api.get<ApplicationResponse>(`/admin/applications/${id}`, { token, signal });
}

/**
 * The application's audit timeline, oldest first.
 *
 * Admin-scoped twin of `getApplicationHistory`: same event ordering and audit
 * fields, with `actor_email` and `agency_name` enriched on the server so the
 * timeline can say who acted without exposing anything else about the user.
 */
export function getAdminApplicationHistory(
  id: string,
  { token, signal }: CallOptions,
): Promise<AdminApplicationHistoryResponse> {
  return api.get<AdminApplicationHistoryResponse>(`/admin/applications/${id}/history`, {
    token,
    signal,
  });
}

/* --- Admin Agencies ------------------------------------------------------- */

/**
 * The city's agencies, ordered by name server-side.
 *
 * Paginated like the other admin lists: the server caps `limit` at 100, so a
 * large city is reached through offset pages rather than one wide request.
 */
export function listAdminAgencies(
  params: { offset?: number; limit?: number },
  { token, signal }: CallOptions,
): Promise<AgencyResponse[]> {
  const search = query({ offset: params.offset, limit: params.limit ?? PAGE_SIZE });
  return api.get<AgencyResponse[]>(`/admin/agencies${search}`, { token, signal });
}

export function getAdminAgency(id: string, { token, signal }: CallOptions) {
  return api.get<AgencyResponse>(`/admin/agencies/${id}`, { token, signal });
}

/** 201 with the created agency, or 409 when the name already exists in the city. */
export function createAdminAgency(payload: AgencyWrite, { token, signal }: CallOptions) {
  return api.post<AgencyResponse>("/admin/agencies", payload, { token, signal });
}

/** Renames one agency. 409 when another agency already holds the name. */
export function updateAdminAgency(
  id: string,
  payload: AgencyWrite,
  { token, signal }: CallOptions,
) {
  return api.patch<AgencyResponse>(`/admin/agencies/${id}`, payload, { token, signal });
}

/**
 * 204 on success. 409 when routing rules or review tasks still reference the
 * agency — the server's message says which, and the UI shows it verbatim.
 */
export function deleteAdminAgency(id: string, { token, signal }: CallOptions): Promise<void> {
  return api.delete<void>(`/admin/agencies/${id}`, { token, signal });
}

/* --- Admin Users ---------------------------------------------------------- */

/**
 * Every user in the admin's city, server-sorted and searchable.
 *
 * `q` is matched against email and `sort`/`order` set the column order in the
 * database, so "load more" pages a single stable result set rather than
 * whatever slice happens to be in the browser. Defaults stay newest first.
 * Same pagination contract as the other admin lists (server caps `limit` at
 * 100). The response is deliberately hash-free: `AdminUserResponse` is the only
 * user shape this API ever returns.
 */
export function listAdminUsers(
  params: AdminUserListParams,
  { token, signal }: CallOptions,
): Promise<AdminUserResponse[]> {
  const search = query({
    q: params.q,
    sort: params.sort,
    order: params.order,
    offset: params.offset,
    limit: params.limit ?? PAGE_SIZE,
  });
  return api.get<AdminUserResponse[]>(`/admin/users${search}`, { token, signal });
}

export function getAdminUser(id: string, { token, signal }: CallOptions) {
  return api.get<AdminUserResponse>(`/admin/users/${id}`, { token, signal });
}

/**
 * 201 with the created user.
 *
 * 409 when the email already exists; 422 when the role/agency combination is
 * invalid (reviewer without an agency, or an agency for any other role).
 */
export function createAdminUser(payload: AdminUserCreate, { token, signal }: CallOptions) {
  return api.post<AdminUserResponse>("/admin/users", payload, { token, signal });
}

/**
 * Sparse update of email, password, and — for Agency Reviewers only — agency.
 *
 * There is no role field: the server rejects one, so the UI never offers role
 * editing. `agency_id: null` is ignored server-side, so an agency can be moved
 * but never cleared.
 */
export function updateAdminUser(
  id: string,
  payload: AdminUserUpdate,
  { token, signal }: CallOptions,
) {
  return api.patch<AdminUserResponse>(`/admin/users/${id}`, payload, { token, signal });
}

/**
 * 204 on success. 403 when the target is the signed-in user, 409 when the
 * user has authored audit events — both shown verbatim to the admin.
 */
export function deleteAdminUser(id: string, { token, signal }: CallOptions): Promise<void> {
  return api.delete<void>(`/admin/users/${id}`, { token, signal });
}

/* --- Admin Routing -------------------------------------------------------- */

/**
 * Every routing rule in the admin's city: one row per (event_type, agency)
 * pair, ordered by event type then agency name server-side.
 *
 * This endpoint — not `/routing/matrix` — is the source of truth for the UI:
 * the matrix returns agency *names* only, which cannot drive removal or
 * duplicate checks, while this list carries `agency_id` alongside the name.
 * The full grid is reconstructed client-side from `EVENT_TYPES`, which gives
 * the same empty rows the matrix endpoint defaults in.
 *
 * No pagination parameters exist: the server returns the complete set.
 */
export function listAdminRoutingRules({ token, signal }: CallOptions): Promise<RoutingRule[]> {
  return api.get<RoutingRule[]>("/admin/routing", { token, signal });
}

/**
 * 201 with the created rule.
 *
 * 409 when the (event_type, agency) pair already exists; 422 for an invalid
 * event type (string detail listing the expected values); 404 when the agency
 * is not in this city.
 */
export function createAdminRoutingRule(
  payload: RoutingRuleCreate,
  { token, signal }: CallOptions,
) {
  return api.post<RoutingRule>("/admin/routing", payload, { token, signal });
}

/**
 * 204 on success; 404 when the rule no longer exists.
 *
 * The event type goes in the path and `"Street Fair"` contains a space, so
 * the segment is percent-encoded explicitly rather than left to `fetch`.
 */
export function deleteAdminRoutingRule(
  eventType: EventType,
  agencyId: string,
  { token, signal }: CallOptions,
): Promise<void> {
  const type = encodeURIComponent(eventType);
  return api.delete<void>(`/admin/routing/${type}/${encodeURIComponent(agencyId)}`, {
    token,
    signal,
  });
}