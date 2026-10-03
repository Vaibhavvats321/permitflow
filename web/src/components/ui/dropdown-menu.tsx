"use client";

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Dropdown menu, used for the account menu and for row-level overflow actions.
 *
 * A table row's actions live here rather than as three inline buttons, because
 * three buttons per row turns a five-column table into a wall of repeated
 * controls and pushes the actual data off screen.
 */

const DropdownMenu = DropdownMenuPrimitive.Root;
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
const DropdownMenuGroup = DropdownMenuPrimitive.Group;

const DropdownMenuContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(function DropdownMenuContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          "animate-pop-in z-50 min-w-[12rem] overflow-hidden rounded-panel",
          "border border-line bg-surface p-1 shadow-floating",
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
});

const DropdownMenuItem = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & {
    tone?: "default" | "danger";
  }
>(function DropdownMenuItem({ className, tone = "default", ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Item
      ref={ref}
      className={cn(
        "flex cursor-pointer select-none items-center gap-2.5 rounded-control px-2.5 py-1.5",
        "text-[13px] outline-none transition-colors",
        "[&_svg]:size-3.5 [&_svg]:shrink-0 [&_svg]:text-ink-400",
        "data-[highlighted]:bg-ink-50",
        "data-[disabled]:pointer-events-none data-[disabled]:text-ink-400",
        tone === "danger"
          ? "text-critical data-[highlighted]:bg-critical-soft data-[highlighted]:text-critical-ink"
          : "text-ink-700 data-[highlighted]:text-ink-900",
        className,
      )}
      {...props}
    />
  );
});

const DropdownMenuLabel = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label>
>(function DropdownMenuLabel({ className, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Label
      ref={ref}
      className={cn("px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400", className)}
      {...props}
    />
  );
});

const DropdownMenuSeparator = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>
>(function DropdownMenuSeparator({ className, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Separator
      ref={ref}
      className={cn("my-1 h-px bg-line", className)}
      {...props}
    />
  );
});

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
};