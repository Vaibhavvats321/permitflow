"use client";

import * as AvatarPrimitive from "@radix-ui/react-avatar";
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Avatar, separator and tooltip — the three small primitives that keep a dense
 * layout from falling apart.
 *
 * The avatar is a pure initial-based one because the API returns no avatar URL
 * and no display name beyond an email; inventing a photo field would mean the
 * image never loads.
 */

export const Avatar = forwardRef<
  HTMLSpanElement,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root>
>(function Avatar({ className, ...props }, ref) {
  return (
    <AvatarPrimitive.Root
      ref={ref}
      className={cn(
        "relative flex size-8 shrink-0 overflow-hidden rounded-full",
        "bg-brand-100 ring-1 ring-inset ring-brand-200",
        className,
      )}
      {...props}
    />
  );
});

export const AvatarFallback = forwardRef<
  HTMLSpanElement,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Fallback>
>(function AvatarFallback({ className, ...props }, ref) {
  return (
    <AvatarPrimitive.Fallback
      ref={ref}
      className={cn(
        "flex size-full items-center justify-center text-[11px] font-semibold uppercase text-brand-700",
        className,
      )}
      {...props}
    />
  );
});

/** The first character of an email address, uppercased. */
export function initialFromEmail(email: string | null | undefined): string {
  const first = email?.trim().charAt(0);
  return first ? first.toUpperCase() : "?";
}

export const Separator = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(function Separator({ className, orientation = "horizontal", decorative = true, ...props }, ref) {
  return (
    <SeparatorPrimitive.Root
      ref={ref}
      orientation={orientation}
      decorative={decorative}
      className={cn(
        "shrink-0 bg-line",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      {...props}
    />
  );
});

/**
 * Tooltip provider. One at the shell root rather than per-tooltip: Radix requires
 * a provider for delays to be shared, and mounting many of them produces
 * tooltips that disagree about how long to wait.
 */
export const TooltipProvider = TooltipPrimitive.Provider;

export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(function TooltipContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          "animate-pop-in z-50 max-w-64 rounded-control bg-ink-900 px-2.5 py-1.5",
          "text-xs leading-relaxed text-ink-50 shadow-floating",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
});

/**
 * Tooltip with an inline icon trigger, for the "what does this status mean?"
 * affordance next to a status badge.
 */
export function InfoTooltip({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}