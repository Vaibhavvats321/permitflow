import type { ApplicationStatus, ReviewStatus, UserRole } from "./types";

/**
 * The single source of truth for how a status looks.
 *
 * Badges, progress bars, decision panels and list accents all read from here.
 * That is the whole point: if four components each picked their own green, the
 * interface would drift into four slightly different greens the first time
 * someone adjusted one of them. Centralising it means the palette stays
 * coherent by construction.
 *
 * Tokens are semantic (`positive`, `attention`, `critical`) rather than literal
 * colours, so the mapping lives in `globals.css` and this file only decides
 * meaning.
 */

export type StatusTone =
  | "neutral"
  | "info"
  | "progress"
  | "positive"
  | "attention"
  | "critical";

export interface StatusPresentation {
  label: string;
  tone: StatusTone;
  /** Sentence-case explanation for tooltips and legends. */
  description: string;
}

/** The bar colour for a review-progress track. Bare, for direct class use. */
export function toneBarClass(tone: StatusTone) {
  switch (tone) {
    case "neutral":
      return "bg-ink-300";
    case "info":
      return "bg-info";
    case "progress":
      return "bg-brand-500";
    case "positive":
      return "bg-positive";
    case "attention":
      return "bg-attention";
    case "critical":
      return "bg-critical";
  }
}

/** The solid dot colour for a status marker. */
export function toneDotClass(tone: StatusTone) {
  return toneBarClass(tone);
}

const APPLICATION_STATUS: Record<ApplicationStatus, StatusPresentation> = {
  Draft: {
    label: "Draft",
    tone: "neutral",
    description: "Not submitted yet. Only you can see this.",
  },
  Submitted: {
    label: "Submitted",
    tone: "info",
    description: "Sent to the required agencies. No decisions yet.",
  },
  "Under Review": {
    label: "Under Review",
    tone: "progress",
    description: "At least one agency has decided; others are still open.",
  },
  Approved: {
    label: "Approved",
    tone: "positive",
    description: "Every required agency approved. The permit is cleared.",
  },
  Rejected: {
    label: "Rejected",
    tone: "critical",
    description: "An agency declined. This application cannot be resubmitted.",
  },
  "Changes Requested": {
    label: "Changes Requested",
    tone: "attention",
    description: "An agency needs corrections. Edit and resubmit.",
  },
};

const REVIEW_STATUS: Record<ReviewStatus, StatusPresentation> = {
  Pending: {
    label: "Awaiting review",
    tone: "progress",
    description: "Assigned to the agency. No decision recorded yet.",
  },
  Approved: {
    label: "Approved",
    tone: "positive",
    description: "The agency approved this application.",
  },
  Rejected: {
    label: "Rejected",
    tone: "critical",
    description: "The agency rejected this application.",
  },
  "Changes Requested": {
    label: "Changes requested",
    tone: "attention",
    description: "The agency asked the organizer for corrections.",
  },
};

export function applicationStatus(status: ApplicationStatus): StatusPresentation {
  return APPLICATION_STATUS[status] ?? { label: status, tone: "neutral", description: "" };
}

export function reviewStatus(status: ReviewStatus): StatusPresentation {
  return REVIEW_STATUS[status] ?? { label: status, tone: "neutral", description: "" };
}

/**
 * Statuses the organizer can still act on. Drives which actions the detail page
 * offers, so the UI cannot present a submit button for an approved application.
 */
export function isEditable(status: ApplicationStatus): boolean {
  return status === "Draft" || status === "Changes Requested";
}

export function canSubmit(status: ApplicationStatus): boolean {
  return status === "Draft";
}

export function canResubmit(status: ApplicationStatus): boolean {
  return status === "Changes Requested";
}

/* --- Roles ---------------------------------------------------------------- */

const ROLE: Record<UserRole, { label: string; short: string; description: string }> = {
  Organizer: {
    label: "Organizer",
    short: "Organizer",
    description: "Applies for permits and tracks agency reviews.",
  },
  "Agency Reviewer": {
    label: "Agency reviewer",
    short: "Reviewer",
    description: "Reviews applications assigned to their agency.",
  },
  "City Admin": {
    label: "City admin",
    short: "Admin",
    description: "Manages city-wide policy.",
  },
};

export function rolePresentation(role: UserRole) {
  return ROLE[role] ?? { label: role, short: role, description: "" };
}

export function homePathForRole(role: UserRole): string {
  switch (role) {
    case "Organizer":
      return "/dashboard";
    case "Agency Reviewer":
      return "/queue";
    // City Admin has no backend surface yet, so it gets the honest empty state
    // rather than a route that would have to invent data to render.
    case "City Admin":
      return "/admin-dashboard";
  }
}

/* --- Audit actions -------------------------------------------------------- */

export type AuditKind = "neutral" | "positive" | "attention" | "critical" | "info";

const AUDIT_ACTIONS: Record<string, { label: string; kind: AuditKind }> = {
  "application.created": { label: "Application created", kind: "neutral" },
  "application.updated": { label: "Application edited", kind: "neutral" },
  "application.submitted": { label: "Submitted for review", kind: "info" },
  "application.resubmitted": { label: "Resubmitted after changes", kind: "info" },
  "review.approved": { label: "Review approved", kind: "positive" },
  "review.rejected": { label: "Review rejected", kind: "critical" },
  "review.changes_requested": { label: "Changes requested", kind: "attention" },
};

export function auditPresentation(action: string) {
  return (
    AUDIT_ACTIONS[action] ?? {
      label: action.replace(/[._]/g, " "),
      kind: "neutral" as AuditKind,
    }
  );
}

/* --- Event types ---------------------------------------------------------- */

export function eventTypeDescription(type: string): string {
  switch (type) {
    case "Marathon":
      return "Road race or running event";
    case "Concert":
      return "Ticketed or public performance";
    case "Street Fair":
      return "Open public gathering";
    default:
      return "Other permitted activity";
  }
}

