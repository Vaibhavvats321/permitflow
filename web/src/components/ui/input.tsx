"use client";

import * as LabelPrimitive from "@radix-ui/react-label";
import { AlertCircle } from "lucide-react";
import {
  createContext,
  forwardRef,
  useContext,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/cn";

/**
 * Form controls.
 *
 * `Field` is the piece that matters here. Label, control, hint and error are one
 * unit, and wiring up the three `id`s that keeps them associated
 * (`htmlFor`, `aria-describedby`, `aria-invalid`) is exactly the work that gets
 * skipped when each control is written separately — which is how an enterprise
 * form ends up with a red border and no explanation of what is wrong.
 */

const controlBase = [
  "w-full rounded-control border bg-surface text-sm text-ink-900",
  "placeholder:text-ink-400",
  "transition-[border-color,box-shadow] duration-150",
  "focus:outline-none focus-visible:outline-none",
  "disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:text-ink-400",
  "aria-[invalid=true]:border-critical",
  "aria-[invalid=true]:focus:shadow-[0_0_0_3px_rgb(220_38_38/0.12)]",
];

export function Label({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn(
        "text-[13px] font-medium text-ink-700 peer-disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  /** Static trailing content, e.g. a unit such as "attendees". */
  trailing?: ReactNode;
  leading?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, trailing, leading, ...props },
  ref,
) {
  // An explicit `invalid` prop wins over the enclosing Field's state, so a field
  // that is deliberately marked invalid can override the context.
  const fieldAria = useFieldAria(props);
  const invalidAria = invalid ?? fieldAria.invalid;

  const control = (
    <input
      ref={ref}
      className={cn(
        controlBase,
        "h-9 px-3",
        leading && "pl-9",
        trailing && "pr-14",
        "focus:border-brand-400 focus:shadow-[0_0_0_3px_rgb(99_102_241/0.14)]",
        className,
      )}
      {...props}
      // After the spread: these are owned by `Field` and must not be clobbered.
      aria-invalid={invalidAria}
      aria-describedby={fieldAria.describedBy}
    />
  );

  if (!leading && !trailing) return control;

  return (
    <div className="relative">
      {leading && (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400 [&_svg]:size-4">
          {leading}
        </span>
      )}
      {control}
      {trailing && (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[13px] text-ink-400">
          {trailing}
        </span>
      )}
    </div>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ className, invalid, ...props }, ref) {
    const fieldAria = useFieldAria(props);
    return (
      <textarea
        ref={ref}
        className={cn(
          controlBase,
          "min-h-24 resize-y px-3 py-2 leading-relaxed",
          "focus:border-brand-400 focus:shadow-[0_0_0_3px_rgb(99_102_241/0.14)]",
          className,
        )}
        {...props}
        aria-invalid={invalid ?? fieldAria.invalid}
        aria-describedby={fieldAria.describedBy}
      />
    );
  },
);

/**
 * Label, control, optional hint, optional error. Renders a real `<label>` bound
 * to the control and an `aria-describedby` that names *both* the hint and the
 * error when both exist, so a screen reader hears the reason for the failure
 * without losing the guidance above it.
 *
 * The error is a `role="alert"`: a validation message that only appears after a
 * submit attempt has to be announced, otherwise a screen-reader user is told
 * nothing happened.
 */
export function Field({
  label,
  hint,
  error,
  required,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  htmlFor: string;
  children: ReactNode;
  className?: string;
}) {
  const describedBy =
    [hint ? `${htmlFor}-hint` : null, error ? `${htmlFor}-error` : null]
      .filter(Boolean)
      .join(" ") || undefined;

  return (
    <FieldGroupContext.Provider value={{ describedBy, invalid: Boolean(error) }}>
      <div className={cn("flex flex-col gap-1.5", className)}>
        <Label htmlFor={htmlFor}>
          {label}
          {required && (
            <span className="ml-0.5 text-critical" aria-hidden>
              *
            </span>
          )}
        </Label>
        {children}
        {/*
          Both hint and error are kept in the DOM when both are present. Swapping
          one for the other loses context exactly when the user most needs it.
        */}
        {hint && (
          <p id={`${htmlFor}-hint`} className="text-[13px] leading-relaxed text-ink-500">
            {hint}
          </p>
        )}
        {error && (
          <p
            id={`${htmlFor}-error`}
            role="alert"
            className="flex items-start gap-1.5 text-[13px] font-medium text-critical"
          >
            <AlertCircle aria-hidden className="mt-px size-3.5 shrink-0" />
            {error}
          </p>
        )}
      </div>
    </FieldGroupContext.Provider>
  );
}

/**
 * Wiring `aria-describedby` and `aria-invalid` from the enclosing `Field`.
 *
 * A `Field` owns the ids, so the control inside it cannot know them at the point
 * it is written. Context keeps `aria-describedby` from drifting out of sync when
 * a field gains an error — the failure mode where the message renders but the
 * input never points at it.
 */
const FieldGroupContext = createContext<{ describedBy?: string; invalid: boolean }>({
  describedBy: undefined,
  invalid: false,
});

/**
 * Merge caller-supplied `aria-describedby` with the one the `Field` owns.
 *
 * Takes the props object rather than the two values so it works with any element
 * prop bag without each caller having to narrow the attribute's type.
 */
function useFieldAria(props: {
  "aria-describedby"?: string;
  "aria-invalid"?: unknown;
}) {
  const group = useContext(FieldGroupContext);

  const describedBy =
    [group.describedBy, props["aria-describedby"]].filter(Boolean).join(" ") || undefined;

  // Anything other than the string tokens is meaningless for our styling hook
  // (`aria-[invalid=true]`), so treat it as absent and let the Field decide.
  const explicit = props["aria-invalid"];
  const invalid =
    explicit === "true" || explicit === true
      ? true
      : group.invalid || undefined;

  return { describedBy, invalid };
}

/** Convenience wrapper that owns the generated ids and wires them together. */
export function TextField({
  label,
  hint,
  error,
  required,
  className,
  ...props
}: Omit<InputProps, "id"> & {
  label: string;
  hint?: ReactNode;
  error?: string;
}) {
  const generated = useId();
  const id = props.name ?? generated;

  return (
    <Field
      label={label}
      hint={hint}
      error={error}
      required={required}
      htmlFor={id}
      className={className}
    >
      {/* No `aria-describedby` here: `Field` supplies it, covering hint and error. */}
      <Input id={id} name={props.name ?? id} required={required} {...props} />
    </Field>
  );
}

export function TextareaField({
  label,
  hint,
  error,
  required,
  className,
  ...props
}: Omit<TextareaProps, "id"> & {
  label: string;
  hint?: ReactNode;
  error?: string;
}) {
  const generated = useId();
  const id = props.name ?? generated;

  return (
    <Field
      label={label}
      hint={hint}
      error={error}
      required={required}
      htmlFor={id}
      className={className}
    >
      {/* No `aria-describedby` here: `Field` supplies it, covering hint and error. */}
      <Textarea id={id} name={props.name ?? id} required={required} {...props} />
    </Field>
  );
}