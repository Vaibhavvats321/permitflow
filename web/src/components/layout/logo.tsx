import { cn } from "@/lib/cn";

/**
 * The product mark.
 *
 * A permit document with a check stroke through it — the two things the product
 * is about. Drawn inline as an SVG rather than loaded from disk so it inherits
 * `currentColor` and stays crisp at any size, with no extra request and no
 * `next/image` configuration for a 20px glyph.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-control",
        "bg-ink-900 text-white",
        className,
      )}
    >
      <svg viewBox="0 0 20 20" fill="none" aria-hidden className="size-4">
        <path
          d="M5.25 3.5h6.5l3 3v9a1 1 0 0 1-1 1h-8.5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path
          d="M11.5 3.6v3h3"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
          opacity="0.55"
        />
        <path
          d="m7.6 11.4 1.7 1.7 3.3-3.6"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

/** The larger wordmark for the marketing header. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <Logo className="size-8 rounded-card" />
      <span className="text-[17px] font-semibold tracking-tight text-ink-900">PermitFlow</span>
    </span>
  );
}