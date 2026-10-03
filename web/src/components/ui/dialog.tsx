"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";

/**
 * Modal dialog.
 *
 * Every irreversible action in this app goes through one of these — submitting an
 * application for review, approving a permit, rejecting one. Confirmation is not
 * decoration: resubmission sends the application back to real agencies and
 * cannot be quietly undone, so the consequence needs stating in words before the
 * click, not just a toast afterwards.
 *
 * The descriptions in this codebase are written to be *specific* about what will
 * happen. "Are you sure?" teaches nothing.
 */

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(function DialogOverlay({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn(
        "animate-overlay-in fixed inset-0 z-50 bg-ink-950/40 backdrop-blur-[2px]",
        className,
      )}
      {...props}
    />
  );
});

const DialogContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
    /** Hide the built-in close button when the dialog demands a decision. */
    hideClose?: boolean;
  }
>(function DialogContent({ className, children, hideClose = false, ...props }, ref) {
  return (
    <DialogPrimitive.Portal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          "animate-content-in fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2",
          "max-h-[calc(100dvh-2rem)] overflow-y-auto",
          "rounded-panel border border-line bg-surface shadow-overlay",
          className,
        )}
        {...props}
      >
        {children}
        {!hideClose && (
          <DialogPrimitive.Close asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="absolute right-4 top-4 text-ink-400 hover:text-ink-700"
            >
              <X aria-hidden />
              <span className="sr-only">Close</span>
            </Button>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
});

function DialogHeader({ className, ...props }: { className?: string; children: ReactNode }) {
  return <div className={cn("flex flex-col gap-1.5 p-6 pb-4 pr-12", className)}>{props.children}</div>;
}

function DialogBody({ className, ...props }: { className?: string; children: ReactNode }) {
  return <div className={cn("px-6 pb-2 text-sm leading-relaxed text-ink-600", className)}>{props.children}</div>;
}

function DialogFooter({ className, ...props }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 px-6 py-5 sm:flex-row sm:justify-end",
        className,
      )}
      {...props}
    >
      {props.children}
    </div>
  );
}

/** A destructive-confirmation dialog with one obvious way out. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "primary",
  loading = false,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogPrimitive.Title className="text-base font-semibold tracking-tight text-ink-900">
            {title}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description asChild>
            <div className="text-sm leading-relaxed text-ink-600">{description}</div>
          </DialogPrimitive.Description>
        </DialogHeader>
        {children && <DialogBody>{children}</DialogBody>}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="default" disabled={loading}>
              {cancelLabel}
            </Button>
          </DialogClose>
          <Button variant={tone} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const DialogTitle = DialogPrimitive.Title;
const DialogDescription = DialogPrimitive.Description;

export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogTitle,
  DialogTrigger,
};