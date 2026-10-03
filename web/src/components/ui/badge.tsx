import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { toneBarClass, toneDotClass, type StatusTone } from "@/lib/status";

/**
 * The badge, used for every status in the product.
 *
 * It reads its tone from the shared status map rather than taking a colour prop,
 * so a status can never be rendered with a tone that contradicts what the same
 * status means on another screen.
 */

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "bg-neutral-soft text-neutral-ink ring-ink-200",
        info: "bg-info-soft text-info-ink ring-info/20",
        progress: "bg-brand-50 text-brand-700 ring-brand-200",
        positive: "bg-positive-soft text-positive-ink ring-positive/20",
        attention: "bg-attention-soft text-attention-ink ring-attention/20",
        critical: "bg-critical-soft text-critical-ink ring-critical/20",
      },
      size: {
        sm: "px-2 py-0.5 text-[11px]",
        md: "px-2.5 py-0.5 text-xs",
      },
    },
    defaultVariants: { tone: "neutral", size: "md" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  /** A leading dot, for statuses in lists where the label alone is not enough. */
  dot?: boolean;
}

export function Badge({
  className,
  tone,
  size,
  dot = false,
  children,
  ...props
}: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone, size }), className)} {...props}>
      {dot && (
        <span
          aria-hidden
          className={cn("size-1.5 rounded-full", toneDotClass(tone ?? "neutral"))}
        />
      )}
      {children}
    </span>
  );
}

/** A badge bound to a status map, so screens never restate the tone. */
export function StatusBadge({
  presentation,
  size = "md",
  dot = true,
  className,
}: {
  presentation: { label: string; tone: StatusTone };
  size?: BadgeProps["size"];
  dot?: boolean;
  className?: string;
}) {
  return (
    <Badge tone={presentation.tone} size={size} dot={dot} className={className}>
      {presentation.label}
    </Badge>
  );
}

/** A small neutral chip for counts and categories. */
export function CountChip({
  value,
  className,
}: {
  value: number | string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "tabular inline-flex min-w-5 items-center justify-center rounded-full",
        "bg-ink-100 px-1.5 py-0.5 text-[11px] font-semibold text-ink-600",
        className,
      )}
    >
      {value}
    </span>
  );
}

/** A thin coloured bar, used for review-progress segments. */
export function ToneBar({ tone, className }: { tone: StatusTone; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("block h-1.5 w-full rounded-full", toneBarClass(tone), className)}
    />
  );
}