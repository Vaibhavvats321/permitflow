import { cn } from "@/lib/cn";

/**
 * Skeletons.
 *
 * Shimmer rather than pulse: a pulsing block reads as "this is broken, retrying",
 * while a slow sweep reads as "this is loading" and keeps the layout stable
 * enough that nothing jumps when the data lands.
 *
 * `SkeletonText` exists because a paragraph of skeleton rectangles at a fixed
 * height looks like a paragraph, and getting the line count right is most of the
 * work of a good loading state.
 */

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn("skeleton rounded-control", className)} {...props} />;
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className="h-3.5"
          // The last line is short, as a real paragraph's would be.
          style={index === lines - 1 ? { width: "62%" } : undefined}
        />
      ))}
    </div>
  );
}

/** A placeholder row shaped like a table row, for list and table loading states. */
export function SkeletonRows({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="divide-y divide-line">
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} className="flex items-center gap-4 px-5 py-3.5">
          {Array.from({ length: columns }, (_, columnIndex) => (
            <Skeleton
              key={columnIndex}
              className="h-3.5"
              style={{
                flex: columnIndex === 0 ? "2" : "1",
                maxWidth: columnIndex === 0 ? "40%" : undefined,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/** A placeholder card, matching `StatCard`'s proportions. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-card border border-line bg-surface p-5", className)}>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-7 w-16" />
      <Skeleton className="mt-4 h-1.5 w-full rounded-full" />
    </div>
  );
}

/**
 * A busy indicator with an accessible label.
 *
 * `role="status"` plus visually hidden text means the loading state is announced
 * rather than being visible only — a spinner alone tells a screen reader nothing.
 */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2.5 py-16 text-sm text-ink-500">
      <svg className="size-4 animate-spin text-ink-400" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      {label}
    </div>
  );
}