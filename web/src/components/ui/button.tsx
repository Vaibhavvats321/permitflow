"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Buttons.
 *
 * Four variants rather than a generic "primary/secondary" pair, because this app
 * has four genuinely different intents: a neutral default, the single primary
 * action on a screen, a destructive action on someone's permit, and a quiet
 * inline action. Collapsing those into one scale is what makes dashboards look
 * like dashboards.
 *
 * Every variant shares one focus ring, one radius and one disabled treatment so
 * they read as one material.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control",
    "text-sm font-medium transition-[background-color,border-color,color,box-shadow]",
    "duration-150 ease-[var(--ease-out-soft)]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary: "bg-brand-600 text-white shadow-raised hover:bg-brand-700 active:bg-brand-800",
        default:
          "border border-line-strong bg-surface text-ink-800 shadow-raised hover:bg-surface-muted hover:border-ink-300 active:bg-surface-sunken",
        ghost: "text-ink-600 hover:bg-ink-50 hover:text-ink-900",
        danger: "bg-critical text-white shadow-raised hover:bg-critical-ink active:bg-critical-ink",
        subtle:
          "bg-brand-50 text-brand-700 hover:bg-brand-100 active:bg-brand-100",
      },
      size: {
        sm: "h-8 px-3 text-[13px] [&_svg]:size-3.5",
        md: "h-9 px-3.5 [&_svg]:size-4",
        lg: "h-10 px-4 [&_svg]:size-4",
        icon: "size-9 [&_svg]:size-4",
        "icon-sm": "size-8 [&_svg]:size-3.5",
      },
      block: {
        true: "w-full",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render the child element instead of a `<button>`, keeping the styling. */
  asChild?: boolean;
  /** Shows a spinner and disables the control. Implies the action is running. */
  loading?: boolean;
  icon?: ReactNode;
  iconAfter?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant,
    size,
    block,
    asChild = false,
    loading = false,
    icon,
    iconAfter,
    children,
    disabled,
    type,
    ...props
  },
  ref,
) {
/*
   * `Slot` merges its props onto exactly one child element, so it cannot be given
   * a sibling icon node: three children is not a single element and Radix throws
   * at render time. With `asChild` the icon therefore belongs inside the child —
   * `<Button asChild icon={<Plus />}><Link>…</Link></Button>` is a crash, so
   * callers write `<Link><Plus />New application</Link>` instead.
   *
   * `loading` is dropped for the same reason rather than silently rendering a
   * spinner outside the slotted element.
   */
  if (asChild) {
    return (
      <Slot
        ref={ref}
        className={cn(buttonVariants({ variant, size, block }), className)}
        aria-busy={loading || undefined}
        {...props}
      >
        {children}
      </Slot>
    );
  }

  return (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, block }), className)}
      disabled={disabled || loading}
      // Buttons inside a form default to `submit`, which turns a stray Enter
      // keypress into an unintended submission. Opting out by default and
      // setting it explicitly is the safer direction.
      type={type ?? "button"}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Loader2 aria-hidden className="animate-spin" /> : icon}
      {children}
      {!loading && iconAfter}
    </button>
  );
});

export { buttonVariants };