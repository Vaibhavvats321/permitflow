import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/**
 * Cards and panels.
 *
 * One radius and one resting shadow, both from the token scale. `Card` is the
 * default container for a bounded piece of content; `Panel` is the same thing
 * with a header/footer region already provided, because the header pattern
 * (title, optional description, optional action) repeats on every screen and was
 * going to diverge otherwise.
 */

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Remove the padding, for cards whose first child manages its own. */
  flush?: boolean;
  /** A brighter border, for a card that is the page's focus. */
  emphasis?: boolean;
}

export function Card({
  className,
  flush = false,
  emphasis = false,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card border bg-surface shadow-raised",
        emphasis ? "border-line-strong" : "border-line",
        !flush && "p-5",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-start justify-between gap-4 p-5 pb-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn("text-sm font-semibold tracking-tight text-ink-900", className)} {...props} />
  );
}

export function CardDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("mt-1 text-[13px] leading-relaxed text-ink-500", className)} {...props} />;
}

export function CardFooter({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 border-t border-line bg-surface-muted px-5 py-3.5",
        "rounded-b-card",
        className,
      )}
      {...props}
    />
  );
}

/** A titled region with an optional action on the right. */
export function Panel({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-card border border-line bg-surface shadow-raised max-w-full", className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold tracking-tight text-ink-900">{title}</h2>}
            {description && (
              <p className="mt-1 text-[13px] leading-relaxed text-ink-500">{description}</p>
            )}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={cn("p-5 overflow-x-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

/** A label/value pair in a definition grid. */
export function DetailRow({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-6", className)}>
      <dt className="w-44 shrink-0 text-[13px] font-medium text-ink-500">{label}</dt>
      <dd className="min-w-0 flex-1 text-sm text-ink-900">{children}</dd>
    </div>
  );
}

/** Dividers between `DetailRow`s, drawn as a bottom border on each row. */
export function DetailList({ className, ...props }: HTMLAttributes<HTMLDListElement>) {
  return (
    <dl className={cn("divide-y divide-line", className)} {...props} />
  );
}