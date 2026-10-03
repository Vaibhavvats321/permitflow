/**
 * Wire types mirrored from the FastAPI schemas.
 *
 * Every union here corresponds to a Python `str, Enum` on the server, and the
 * string values are the enum *values*, not the member names — `ApplicationStatus`
 * serialises as `"Under Review"`, not `"UNDER_REVIEW"`. Queries use the same
 * values, so a status constant doubles as a valid `?status=` filter value.
 *
 * Nothing in this file invents a field. If the UI needs a name the API does not
 * send (a tenant or city name, for instance), the UI does not get to invent one.
 */

/* --- Enums ---------------------------------------------------------------- */

export const APPLICATION_STATUSES = [
  "Draft",
  "Submitted",
  "Under Review",
  "Approved",
  "Rejected",
  "Changes Requested",
] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const REVIEW_STATUSES = [
  "Pending",
  "Approved",
  "Rejected",
  "Changes Requested",
] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const EVENT_TYPES = [
  "Marathon",
  "Concert",
  "Street Fair",
  "Other",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const USER_ROLES = [
  "Organizer",
  "Agency Reviewer",
  "City Admin",
] as const;
export type UserRole = (typeof USER_ROLES)[number];

export const REVIEW_ACTIONS = [
  "approve",
  "reject",
  "request_changes",
] as const;
export type ReviewAction = (typeof REVIEW_ACTIONS)[number];

/* --- Auth ----------------------------------------------------------------- */

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  tenant_id: string;
}

export interface UserResponse {
  id: string;
  email: string;
  role: UserRole;
  tenant_id: string;
  agency_id: string | null;
}

/* --- Applications --------------------------------------------------------- */

/** `PUT /applications/{id}` is a full replacement, so create and update match. */
export interface ApplicationWrite {
  event_name: string;
  event_type: EventType;
  start_date: string | null;
  end_date: string | null;
  location: string | null;
  expected_attendance: number | null;
  description: string | null;
}

export interface AgencyReviewStatus {
  agency_id: string;
  agency_name: string;
  review_status: ReviewStatus;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationResponse extends ApplicationWrite {
  id: string;
  status: ApplicationStatus;
  submitter_id: string;
  tenant_id: string;
  created_at: string;
  updated_at: string;
  /** Empty for a draft: nothing has been sent to anyone yet. */
  reviews: AgencyReviewStatus[];
}

export interface RequiredAgency {
  id: string;
  name: string;
}

export interface SubmitApplicationResponse {
  application: ApplicationResponse;
  required_agencies: RequiredAgency[];
  attendance_override_applied: boolean;
}

export interface ResubmitApplicationResponse {
  application: ApplicationResponse;
  reset_agencies: RequiredAgency[];
  preserved_agencies: RequiredAgency[];
  still_pending_agencies: RequiredAgency[];
}

/* --- Reviews -------------------------------------------------------------- */

/**
 * The application as a reviewer sees it. Deliberately lacks `submitter_id` and
 * `tenant_id`: the server does not send them and the agency has no use for them.
 */
export interface ReviewTaskApplication {
  id: string;
  event_name: string;
  event_type: EventType;
  start_date: string | null;
  end_date: string | null;
  location: string | null;
  expected_attendance: number | null;
  description: string | null;
  status: ApplicationStatus;
}

export interface ReviewTaskResponse {
  id: string;
  application_id: string;
  agency_id: string;
  review_status: ReviewStatus;
  comment: string | null;
  created_at: string;
  updated_at: string;
  application: ReviewTaskApplication;
}

export interface ReviewActionResponse {
  task: ReviewTaskResponse;
  application_status: ApplicationStatus;
}

/* --- History -------------------------------------------------------------- */

export interface AuditEvent {
  id: string;
  application_id: string;
  user_id: string | null;
  agency_id: string | null;
  action: string;
  old_status: string | null;
  new_status: string | null;
  comment: string | null;
  created_at: string;
}

export interface ApplicationHistoryResponse {
  application_id: string;
  application_status: ApplicationStatus;
  events: AuditEvent[];
}

/**
 * One audit event as the admin history endpoint returns it: the shared audit
 * fields plus actor email and agency name, enriched by outer joins. Both are
 * optional here because the organizer and reviewer endpoints return the plain
 * `AuditEvent` without them — they are an admin-view addition, not a change to
 * the event itself, and a system-generated event still arrives with `null`.
 */
export interface AdminAuditEvent extends AuditEvent {
  actor_email?: string | null;
  agency_name?: string | null;
}

export interface AdminApplicationHistoryResponse {
  application_id: string;
  application_status: ApplicationStatus;
  events: AdminAuditEvent[];
}

/* --- Query parameters ----------------------------------------------------- */

export interface ApplicationListParams {
  /** Free-text search, matched by the server across the whole tenant. */
  q?: string;
  status?: ApplicationStatus;
  event_type?: EventType;
  offset?: number;
  limit?: number;
}

export interface ReviewTaskListParams {
  status?: ReviewStatus;
  event_type?: EventType;
  offset?: number;
  limit?: number;
}

/** Matches the server-side `limit` cap, so the UI never asks for more. */
export { PAGE_SIZE } from "./constants";

/* --- Admin Agencies ------------------------------------------------------- */

/**
 * An agency as the admin endpoints return it: id, name, creation time, and
 * nothing else. There is no active/inactive flag in the contract, so there is
 * none here to render.
 */
export interface AgencyResponse {
  id: string;
  name: string;
  created_at: string;
}

/**
 * Name-only payload for both `POST` and `PATCH /admin/agencies`. The server
 * strips surrounding whitespace and rejects a blank name with a 422, and
 * enforces uniqueness within the tenant with a 409.
 */
export interface AgencyWrite {
  name: string;
}

/* --- Admin Users ---------------------------------------------------------- */

/**
 * A user as the admin endpoints return it: never includes a password hash.
 *
 * `agency_name` is resolved server-side and only populated when the user has
 * an agency — i.e. Agency Reviewers.
 */
export interface AdminUserResponse {
  id: string;
  email: string;
  role: UserRole;
  agency_id: string | null;
  agency_name: string | null;
  created_at: string;
}

/**
 * Payload for `POST /admin/users`.
 *
 * `agency_id` is required by the server for the Agency Reviewer role and must
 * be absent for Organizer and City Admin, so callers send it only for
 * reviewers. Role is fixed at creation — there is no role-change endpoint.
 */
export interface AdminUserCreate {
  email: string;
  password: string;
  role: UserRole;
  agency_id?: string;
}

/**
 * Payload for `PATCH /admin/users/{id}` — exactly the three fields the server
 * accepts. Role and tenant are not editable. `agency_id: null` is ignored
 * server-side (the route only acts on a non-null value), so an agency can be
 * changed but never cleared through this API.
 */
export interface AdminUserUpdate {
  email?: string;
  password?: string;
  agency_id?: string;
}

/* --- Admin Routing -------------------------------------------------------- */

/**
 * One routing rule: which agency reviews which event type.
 *
 * `event_type` is always a valid `EventType` value — the column is a Python
 * enum on the server, and the API validates new values against it. `agency_id`
 * is present (unlike the matrix endpoint's names-only rows), which is what
 * makes removal and duplicate checks possible.
 */
export interface RoutingRule {
  event_type: EventType;
  agency_id: string;
  agency_name: string;
}

/**
 * Payload for `POST /admin/routing` — exactly these two fields; the schema is
 * `extra="forbid"`. There is no edit/patch route: a rule changes only by
 * being created or deleted.
 */
export interface RoutingRuleCreate {
  event_type: EventType;
  agency_id: string;
}

/* --- Admin Dashboard ------------------------------------------------------ */

export interface DashboardSummary {
  total_applications: number;
  draft_applications: number;
  submitted_applications: number;
  under_review_applications: number;
  approved_applications: number;
  rejected_applications: number;
  changes_requested_applications: number;
  average_days_to_decision: number | null;
}