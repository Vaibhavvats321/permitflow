"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Select, built on Radix rather than a native `<select>`.
 *
 * The reason is the option set: event types and statuses render as
 * status-coloured entries, which a native control cannot do. It also gets
 * keyboard navigation and typeahead for free, which is not something to
 * reimplement for a dropdown that a keyboard user has to get through.
 *
 * A native `<select>` is still the better choice for a single-column mobile
 * layout; this is the desktop control.
 */

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger> & {
    invalid?: boolean;
  }
>(function SelectTrigger({ className, invalid, children, ...props }, ref) {
  return (
    <SelectPrimitive.Trigger
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "flex h-9 w-full items-center justify-between gap-2 rounded-control border bg-surface",
        "px-3 text-sm text-ink-900",
        "transition-[border-color,box-shadow] duration-150",
        "data-[placeholder]:text-ink-400",
        "focus:border-brand-400 focus:shadow-[0_0_0_3px_rgb(99_102_241/0.14)] focus:outline-none",
        "disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:text-ink-400",
        "aria-[invalid=true]:border-critical",
        "[&>span]:truncate",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-ink-400" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
});

const SelectContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(function SelectContent({ className, children, position = "popper", ...props }, ref) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={ref}
        position={position}
        sideOffset={6}
        className={cn(
          "animate-pop-in relative z-50 max-h-72 min-w-[10rem] overflow-hidden",
          "rounded-panel border border-line bg-surface shadow-floating",
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
});

const SelectItem = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(function SelectItem({ className, children, ...props }, ref) {
  return (
    <SelectPrimitive.Item
      ref={ref}
      className={cn(
        "relative flex cursor-pointer select-none items-center gap-2 rounded-control py-1.5 pl-2.5 pr-8",
        "text-sm text-ink-800 outline-none transition-colors",
        "data-[highlighted]:bg-ink-50 data-[highlighted]:text-ink-900",
        "data-[state=checked]:font-medium",
        "data-[disabled]:pointer-events-none data-[disabled]:text-ink-400",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2.5">
        <Check aria-hidden className="size-3.5 text-brand-600" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
});

const SelectLabel = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(function SelectLabel({ className, ...props }, ref) {
  return (
    <SelectPrimitive.Label
      ref={ref}
      className={cn("px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400", className)}
      {...props}
    />
  );
});

export { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue };