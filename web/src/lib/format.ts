/**
 * Display formatting.
 *
 * Deliberately uses the browser's locale-aware `Intl` rather than hand-rolled
 * string slicing. A hand-rolled `new Date(iso).toLocaleDateString()` substitute
 * is where "Jan 3" and "Jan 3rd" and "3 Jan" go to disagree with what the user
 * expects, and the same code path is reused by a dozen screens.
 */

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const numberFormatter = new Intl.NumberFormat();

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined): string {
  const date = toDate(value);
  return date ? dateFormatter.format(date) : "—";
}

export function formatDateTime(value: string | null | undefined): string {
  const date = toDate(value);
  return date ? dateTimeFormatter.format(date) : "—";
}

/**
 * A permit date range. Collapses to a single date when both ends match, which
 * is the common case for a one-day event and otherwise reads as a bug in the
 * data.
 */
export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const startDate = toDate(start);
  const endDate = toDate(end);

  if (!startDate && !endDate) return "Dates not set";
  if (!startDate) return `Ends ${dateFormatter.format(endDate!)}`;
  if (!endDate) return `From ${dateFormatter.format(startDate)}`;
  if (startDate.getTime() === endDate.getTime()) {
    return dateFormatter.format(startDate);
  }
  return `${dateFormatter.format(startDate)} – ${dateFormatter.format(endDate)}`;
}

export function formatNumber(value: number | null | undefined): string {
  return typeof value === "number" ? numberFormatter.format(value) : "—";
}

/**
 * Attendance with the thousands separator plus the unit, or a dash.
 *
 * Also the input to the Fire-review hint: the server's threshold is strictly
 * greater than 5,000, so the copy says "more than" rather than "5,000 or more".
 */
export function formatAttendance(value: number | null | undefined): string {
  return typeof value === "number" ? `${numberFormatter.format(value)} attendees` : "—";
}

/** Compact age for timelines: "3 days ago". Absolute dates live in tooltips. */
export function formatRelative(value: string | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];

  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, secondsPerUnit] of units) {
    if (Math.abs(seconds) >= secondsPerUnit) {
      return formatter.format(-Math.round(seconds / secondsPerUnit), unit);
    }
  }
  return formatter.format(-seconds, "second");
}

/** Truncate on a word boundary, for one-line table cells and card summaries. */
export function truncate(value: string, max = 96): string {
  if (value.length <= max) return value;
  const cut = value.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut}…`;
}

/**
 * Turn a `datetime-local` value into the ISO string the API expects.
 *
 * The field is wall-clock time with no offset. The server reads a naive value as
 * UTC, so the client has to say which offset it meant or the event could land on
 * the wrong calendar day depending on where the browser is.
 */
export function toApiTimestamp(localValue: string | null): string | null {
  if (!localValue) return null;
  const date = new Date(localValue);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/**
 * The inverse: render an API timestamp as `YYYY-MM-DDTHH:mm` for a
 * `datetime-local` input. Sliced rather than passed through `toISOString()`
 * because that would convert the value into UTC and then present UTC as local.
 */
export function toLocalInputValue(iso: string | null | undefined): string {
  const date = toDate(iso);
  if (!date) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

/**
 * Title-case an audit action's fallback label.
 * `application.resubmitted` → "Application resubmitted".
 */
export function humanizeAction(action: string): string {
  const spaced = action.replace(/[._]/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Short, non-identifying label for a UUID in dense UI. */
export function shortId(id: string | null | undefined): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}