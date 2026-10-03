"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Tabs, used for the application detail page's Overview / Reviews / History split.
 *
 * Tabbed rather than a scrolling page because an organizer arriving at a
 * submitted application almost always wants one of the three things, and making
 * all three compete for the same screen buries the answer under the audit log.
 */

const Tabs = TabsPrimitive.Root;

const TabsList = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(function TabsList({ className, ...props }, ref) {
  return (
    <TabsPrimitive.List
      ref={ref}
      className={cn(
        "flex items-center gap-1 border-b border-line",
        className,
      )}
      {...props}
    />
  );
});

const TabsTrigger = forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger> & { count?: number }
>(function TabsTrigger({ className, count, children, ...props }, ref) {
  return (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        "relative flex items-center gap-2 px-3 pb-2.5 pt-2 text-[13px] font-medium text-ink-500",
        "transition-colors hover:text-ink-800",
        "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500",
        // The active indicator is a bottom rule rather than a filled pill: it
        // keeps the row height stable and reads as section membership.
        "after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full",
        "after:bg-transparent data-[state=active]:text-ink-900 data-[state=active]:after:bg-brand-600",
        className,
      )}
      {...props}
    >
      {children}
      {typeof count === "number" && (
        <span
          className={cn(
            "tabular rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
            "bg-ink-100 text-ink-600",
            "group-data-[state=active]:bg-brand-50 group-data-[state=active]:text-brand-700",
          )}
        >
          {count}
        </span>
      )}
    </TabsPrimitive.Trigger>
  );
});

const TabsContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(function TabsContent({ className, ...props }, ref) {
  return (
    <TabsPrimitive.Content
      ref={ref}
      className={cn("animate-slide-up focus-visible:outline-none", className)}
      {...props}
    />
  );
});

export { Tabs, TabsContent, TabsList, TabsTrigger };