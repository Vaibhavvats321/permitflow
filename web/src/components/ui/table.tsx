"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useRouter, useSearchParams } from "next/navigation";
import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Table primitives.
 *
 * Deliberately not a grid component. These are plain `<table>` elements with
 * shared cell padding and rules, because a permit list is tabular data that
 * belongs in a table for assistive technology, for spreadsheet-like scanning, and
 * for the browser's own find-in-page.
 *
 * The application list uses cards on small screens and this table from `sm` up.
 * Both render the same data from the same components; only the layout differs.
 */

export const Table = forwardRef<
  HTMLTableElement,
  React.HTMLAttributes<HTMLTableElement>
>(function Table({ className, ...props }, ref) {
  return (
    <div className="w-full max-w-full overflow-x-auto">
      <table
        ref={ref}
        className={cn("w-full border-collapse text-sm", className)}
        {...props}
      />
    </div>
  );
});

export function TableHead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b border-line bg-surface-muted", className)} {...props} />;
}

export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-line", className)} {...props} />;
}

export function TableRow({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("transition-colors hover:bg-surface-muted", className)}
      {...props}
    />
  );
}

export function TableHeadCell({
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        "px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-500",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-5 py-3.5 align-middle text-ink-700", className)} {...props} />;
}

/**
 * A sortable column header.
 *
 * Sorting happens client-side over the loaded page, and the control says so in
 * its accessible label. Presenting it as server-side sorting would be a lie about
 * where the order came from, and the "Load more" pattern means there is only ever
 * one page of data in memory anyway.
 */
export function SortableHeadCell({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
  className,
}: {
  label: string;
  sortKey: string;
  sort: { key: string; direction: "asc" | "desc" };
  onSort: (key: string) => void;
  align?: "left" | "right";
  className?: string;
}) {
  const isActive = sort.key === sortKey;
  const nextDirection = isActive && sort.direction === "asc" ? "desc" : "asc";

  return (
    <TableHeadCell className={cn(align === "right" && "text-right", "p-0", className)}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "flex h-full w-full items-center gap-1 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide",
          "transition-colors hover:text-ink-800",
          isActive ? "text-ink-900" : "text-ink-500",
          align === "right" && "justify-end",
        )}
        aria-label={`Sort by ${label}, currently ${isActive ? sort.direction : "unsorted"}. Next: ${nextDirection}`}
      >
        {label}
        <span aria-hidden className="text-[9px] leading-none">
          {isActive ? (sort.direction === "asc" ? "▲" : "▼") : "▲"}
        </span>
      </button>
    </TableHeadCell>
  );
}

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;

export const PopoverContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(function PopoverContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          "animate-pop-in z-50 rounded-panel border border-line bg-surface p-4 shadow-floating",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
});

/**
 * Filter state lives in the URL, not in component state.
 *
 * A filtered list is a place someone will want to bookmark, share or hit the
 * back button on. Holding filters in `useState` throws all three away, and it
 * makes the back button leave the screen instead of clearing one filter.
 */
export function useQueryParamState(key: string, fallback: string) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const value = searchParams.get(key) ?? fallback;

  function setValue(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === fallback || next === "") {
      params.delete(key);
    } else {
      params.set(key, next);
    }
    // `replace` rather than `push`: changing a filter should not fill the
    // history stack with entries the user has to back through.
    router.replace(`?${params.toString()}`, { scroll: false });
  }

  return [value, setValue] as const;
}

/** A labelled filter control, so a toolbar of selects reads as a form. */
export function FilterField({
  label,
  htmlFor,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label
        htmlFor={htmlFor}
        className="text-[11px] font-semibold uppercase tracking-wide text-ink-500"
      >
        {label}
      </label>
      {children}
    </div>
  );
}