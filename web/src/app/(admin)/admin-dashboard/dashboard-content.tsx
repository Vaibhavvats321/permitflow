"use client";

import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  XCircle,
} from "lucide-react";
import { useCallback, useMemo } from "react";
import { useToken } from "@/lib/auth";
import { getDashboard } from "@/lib/endpoints";
import { DashboardSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { Card, DetailList, DetailRow } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { SkeletonCard, SkeletonRows } from "@/components/ui/skeleton";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { Badge, StatusBadge } from "@/components/ui/badge";

/**
 * The City Admin dashboard.
 *
 * Shows aggregate metrics across all applications in the city.
 * Unlike the organizer dashboard, this is a pure read-only view — the admin
 * does not create or edit applications here.
 *
 * Metrics are derived from the backend's /admin/dashboard endpoint which
 * aggregates across all applications in the city.
 */

interface Stat {
  label: string;
  value: number;
  hint?: string;
  href?: string;
  tone: "neutral" | "info" | "progress" | "positive" | "attention" | "critical";
  icon: React.ReactNode;
}

export function AdminDashboard() {
  const token = useToken();

  const { data, error, isLoading, reload } = useApi<DashboardSummary>(
    useCallback(
      (signal) => getDashboard({ token, signal }),
      [token],
    ),
    [token],
  );

  const stats = useMemo(() => {
    if (!data) return [];

    return [
      {
        label: "Total applications",
        value: data.total_applications,
        hint: "All applications in this city",
        tone: "neutral" as const,
        icon: (
          <FileText
            aria-hidden
            className={cn("size-3.5", "text-ink-500")}
          />
        ),
      },
      {
        label: "Draft",
        value: data.draft_applications,
        hint: "Not yet submitted",
        tone: "neutral" as const,
        icon: (
          <FileText
            aria-hidden
            className={cn("size-3.5", "text-ink-500")}
          />
        ),
      },
      {
        label: "Submitted / Under review",
        value: data.submitted_applications + data.under_review_applications,
        hint: "Awaiting agency decisions",
        href: "/admin/applications?status=Under+Review",
        tone: "progress" as const,
        icon: (
          <Clock
            aria-hidden
            className={cn("size-3.5", "text-brand-600")}
          />
        ),
      },
      {
        label: "Approved",
        value: data.approved_applications,
        hint: "All agencies approved",
        href: "/admin/applications?status=Approved",
        tone: "positive" as const,
        icon: (
          <CheckCircle2
            aria-hidden
            className={cn("size-3.5", "text-positive")}
          />
        ),
      },
      {
        label: "Rejected",
        value: data.rejected_applications,
        hint: "At least one agency declined",
        tone: "critical" as const,
        icon: (
          <XCircle
            aria-hidden
            className={cn("size-3.5", "text-critical")}
          />
        ),
      },
      {
        label: "Changes requested",
        value: data.changes_requested_applications,
        hint: "Sent back for corrections",
        tone: "attention" as const,
        icon: (
          <AlertCircle
            aria-hidden
            className={cn("size-3.5", "text-attention")}
          />
        ),
      },
    ];
  }, [data]);

  if (error) {
    return (
      <>
        <PageHeader
          title="Admin dashboard"
          description="City-wide permit application metrics."
        />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }


  if (isLoading) {
    return (
      <>
        <PageHeader title="Admin dashboard" />
        <PageBody className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <SkeletonCard key={index} />
            ))}
          </div>
          <div className="rounded-card border border-line bg-surface">
            <SkeletonRows rows={3} columns={4} />
          </div>
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Admin dashboard"
        description="City-wide permit application metrics."
        actions={
          <Button asChild variant="primary" size="sm">
            <Link href="/admin/applications">View all applications</Link>
          </Button>
        }
      />
      <PageBody className="space-y-6">
        <StatCards stats={stats} />

        {data && data.total_applications > 0 && (
          <Card className="space-y-4">
            <DetailList>
              <DetailRow label="Total applications">
                <span className="tabular font-mono text-ink-900">
                  {data.total_applications}
                </span>
              </DetailRow>
              <DetailRow label="Average days to decision">
                <span className="tabular font-mono text-ink-900">
                  {data.average_days_to_decision !== null && data.average_days_to_decision !== null
                    ? data.average_days_to_decision < 1
                      ? "< 1 day"
                      : data.average_days_to_decision === 1
                        ? "1 day"
                        : `${data.average_days_to_decision.toFixed(1)} days`
                      : "—"}
                </span>
              </DetailRow>
              <DetailRow label="Status breakdown">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    presentation={{
                      label: "Draft",
                      tone: "neutral",
                    }}
                    size="sm"
                    dot={false}
                  />
                  <Badge tone="info" size="sm" dot={false}>
                    Submitted
                  </Badge>
                  <Badge tone="progress" size="sm" dot={false}>
                    Under Review
                  </Badge>
                  <Badge tone="positive" size="sm" dot={false}>
                    Approved
                  </Badge>
                  <Badge tone="critical" size="sm" dot={false}>
                    Rejected
                  </Badge>
                  <Badge tone="attention" size="sm" dot={false}>
                    Changes Requested
                  </Badge>
                </div>
              </DetailRow>
            </DetailList>
          </Card>
        )}
      </PageBody>
    </>
  );
}

/** A reusable stat card grid. */
function StatCards({ stats }: { stats: Stat[] }) {
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
                {stat.icon}
              </span>
            </div>
            <p className="tabular mt-3 text-3xl font-semibold tracking-tight text-ink-950">
              {stat.value}
            </p>
            {stat.hint && <p className="mt-1.5 text-[13px] text-ink-500">{stat.hint}</p>}
          </>
        );

        return stat.href ? (
          <a
            key={stat.label}
            href={stat.href}
            className="group rounded-card border border-line bg-surface p-5 shadow-raised transition-all duration-150 hover:border-line-strong hover:shadow-floating"
          >
            {body}
          </a>
        ) : (
          <div key={stat.label} className="rounded-card border border-line bg-surface p-5 shadow-raised">
            {body}
          </div>
        );
      })}
    </div>
  );
}

interface Stat {
  label: string;
  value: number;
  hint?: string;
  href?: string;
  tone: "neutral" | "info" | "progress" | "positive" | "attention" | "critical";
  icon: React.ReactNode;
}