"use client";

import { AlertCircle, CheckCircle2, Clock, FileText } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import type { StatusTone } from "@/lib/status";
import type { ApplicationStatus } from "@/lib/types";

/**
 * The dashboard's headline figures.
 *
 * Four tiles, and four is the most this layout can carry without the numbers
 * competing. Deliberately not a chart: an aggregate bar chart of six statuses
 * over a demo dataset would encode nothing the counts do not say more directly.
 *
 * Each tile states its own subject — "3 changes requested" rather than a bare
 * "3" — because a number with no label in a four-up grid is a puzzle, not a
 * metric.
 */

export interface Stat {
  label: string;
  value: number;
  hint?: string;
  href?: string;
  tone: StatusTone;
  icon: typeof FileText;
}

export function StatCards({ stats }: { stats: Stat[] }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {stats.map((stat) => {
        const body = (
          <>
            <div className="flex items-start justify-between gap-3">
              <p className="text-[13px] font-medium text-ink-500">{stat.label}</p>
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-control",
                  stat.tone === "neutral" && "bg-ink-100 text-ink-500",
                  stat.tone === "info" && "bg-info-soft text-info",
                  stat.tone === "progress" && "bg-brand-50 text-brand-600",
                  stat.tone === "positive" && "bg-positive-soft text-positive",
                  stat.tone === "attention" && "bg-attention-soft text-attention",
                  stat.tone === "critical" && "bg-critical-soft text-critical",
                )}
              >
                <stat.icon aria-hidden className="size-3.5" />
              </span>
            </div>
            <p className="tabular mt-3 text-3xl font-semibold tracking-tight text-ink-950">
              {stat.value}
            </p>
            {stat.hint && <p className="mt-1.5 text-[13px] text-ink-500">{stat.hint}</p>}
          </>
        );

        return stat.href ? (
          <Link
            key={stat.label}
            href={stat.href}
            className="group rounded-card border border-line bg-surface p-5 shadow-raised transition-all duration-150 hover:border-line-strong hover:shadow-floating"
          >
            {body}
          </Link>
        ) : (
          <div key={stat.label} className="rounded-card border border-line bg-surface p-5 shadow-raised">
            {body}
          </div>
        );
      })}
    </div>
  );
}

/** Progress bar for per-agency review counts. */
export function ReviewProgressBar({
  total,
  approved,
  pending,
  blocked,
}: {
  total: number;
  approved: number;
  pending: number;
  blocked: number;
}) {
  if (total === 0) return null;

  // Segments are summed from an explicit total rather than as percentages of
  // each other, so a rounding error cannot leave a visible gap at the end.
  const segments = [
    { value: approved, className: "bg-positive", label: `${approved} approved` },
    { value: pending, className: "bg-brand-400", label: `${pending} awaiting review` },
    { value: blocked, className: "bg-attention", label: `${blocked} need attention` },
  ].filter((segment) => segment.value > 0);

  return (
    <div
      className="flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full bg-ink-100"
      role="img"
      aria-label={`${approved} of ${total} agencies approved. ${pending} awaiting review. ${blocked} needing attention.`}
    >
      {segments.map((segment) => (
        <span
          key={segment.label}
          className={cn("h-full first:rounded-l-full last:rounded-r-full", segment.className)}
          style={{ flexGrow: segment.value }}
        />
      ))}
    </div>
  );
}

/** The breakdown line under a progress bar. */
export function ReviewProgressLegend({
  approved,
  pending,
  blocked,
}: {
  approved: number;
  pending: number;
  blocked: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-ink-500">
      {approved > 0 && (
        <span className="flex items-center gap-1.5">
          <CheckCircle2 aria-hidden className="size-3.5 text-positive" />
          {approved} approved
        </span>
      )}
      {pending > 0 && (
        <span className="flex items-center gap-1.5">
          <Clock aria-hidden className="size-3.5 text-brand-500" />
          {pending} awaiting
        </span>
      )}
      {blocked > 0 && (
        <span className="flex items-center gap-1.5">
          <AlertCircle aria-hidden className="size-3.5 text-attention" />
          {blocked} need attention
        </span>
      )}
    </div>
  );
}

/** Roll a set of per-agency review statuses into three counts. */
export function countReviewStates(
  reviews: { review_status: string }[],
): { approved: number; pending: number; blocked: number } {
  let approved = 0;
  let pending = 0;
  let blocked = 0;

  for (const review of reviews) {
    if (review.review_status === "Approved") approved += 1;
    else if (review.review_status === "Pending") pending += 1;
    else blocked += 1;
  }

  return { approved, pending, blocked };
}

/** A one-line status summary for a list row. */
export function StatusLine({
  status,
  reviewCount,
}: {
  status: ApplicationStatus;
  reviewCount: number;
}) {
  if (status === "Draft") {
    return <span className="text-[13px] text-ink-400">Not sent to any agency</span>;
  }
  if (reviewCount === 0) {
    return <span className="text-[13px] text-ink-400">No agencies assigned</span>;
  }
  return (
    <span className="tabular text-[13px] text-ink-500">
      {reviewCount} {reviewCount === 1 ? "agency" : "agencies"} reviewing
    </span>
  );
}