"use client";

import { ChevronRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

/**
 * Page chrome: breadcrumb, title, description, primary action.
 *
 * One component rather than a layout that every screen assembles by hand, because
 * the vertical rhythm between the breadcrumb, the h1, the description and the
 * action is what makes a set of pages feel like one product.
 */

export interface Crumb {
  label: string;
  href?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
  icon: Icon,
  className,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  crumbs?: Crumb[];
  icon?: LucideIcon;
  className?: string;
  /** Rendered under the header row — filters, tabs, badges. */
  children?: ReactNode;
}) {
  return (
    <header className={cn("border-b border-line bg-surface", className)}>
      <div className="px-5 pt-5 sm:px-8 sm:pt-6">
        {crumbs && crumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-2.5">
            <ol className="flex flex-wrap items-center gap-1 text-[13px] text-ink-500">
              {crumbs.map((crumb, index) => (
                <li key={`${crumb.label}-${index}`} className="flex items-center gap-1">
                  {index > 0 && (
                    <ChevronRight aria-hidden className="size-3.5 text-ink-300" />
                  )}
                  {crumb.href ? (
                    <Link
                      href={crumb.href}
                      className="rounded transition-colors hover:text-ink-900"
                    >
                      {crumb.label}
                    </Link>
                  ) : (
                    <span aria-current="page" className="font-medium text-ink-700">
                      {crumb.label}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}

        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="flex min-w-0 items-start gap-3">
            {Icon && (
              <span className="mt-0.5 hidden size-9 shrink-0 items-center justify-center rounded-card border border-line bg-surface-muted sm:flex">
                <Icon aria-hidden className="size-4 text-ink-500" />
              </span>
            )}
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-ink-950 sm:text-[22px]">
                {title}
              </h1>
              {description && (
                <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-500 sm:text-sm">
                  {description}
                </p>
              )}
            </div>
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>

        {children && <div className="mt-4">{children}</div>}
      </div>
    </header>
  );
}

/** The standard page body: constrained width, consistent gutter. */
export function PageBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("px-5 py-6 sm:px-8 sm:py-8 max-w-screen overflow-x-hidden", className)}
      {...props}
    />
  );
}

/** A constrained reading column, for detail pages that should not run full width. */
export function PageNarrow({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <PageBody className={cn("mx-auto w-full max-w-3xl", className)} {...props} />;
}

/** A right-aligned "New application" style action for a list header. */
export function HeaderAction({
  href,
  children,
  icon,
}: {
  href: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  // The icon goes inside the link, not on the Button: `asChild` slots props onto
  // a single element, so a sibling icon node cannot be rendered.
  return (
    <Button asChild variant="primary">
      <Link href={href} className="gap-2">
        {icon}
        {children}
      </Link>
    </Button>
  );
}