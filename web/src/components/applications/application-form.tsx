"use client";

import {
  ArrowLeft,
  CalendarDays,
  Info,
  MapPin,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useToken } from "@/lib/auth";
import { createApplication, getApplication, updateApplication } from "@/lib/endpoints";
import { toApiTimestamp, toLocalInputValue } from "@/lib/format";
import { useApi, useMutation } from "@/lib/use-api";
import { EVENT_TYPES, type ApplicationWrite, type EventType } from "@/lib/types";
import { eventTypeDescription } from "@/lib/status";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Panel } from "@/components/ui/card";
import { InlineError } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { LARGE_EVENT_THRESHOLD } from "@/lib/constants";
import { Field, Input, Textarea } from "@/components/ui/input";

/**
 * The create/edit form.
 *
 * One component serves both routes. The only difference between creating a draft
 * and correcting one is the endpoint, the page title and whether the server
 * already has values — so a second form would be two copies of the same
 * validation and two places for the Fire threshold hint to go stale.
 *
 * Validation is deliberately permissive on purpose. The server decides what makes
 * an application *submittable* (it rejects a submit with a list of missing
 * fields); this form only rejects what the server would reject at write time.
 * Blocking a draft from being saved because it is incomplete would defeat the
 * point of a draft.
 */

interface FormState {
  event_name: string;
  event_type: EventType;
  start_date: string;
  end_date: string;
  location: string;
  expected_attendance: string;
  description: string;
}

const BLANK: FormState = {
  event_name: "",
  event_type: "Concert",
  start_date: "",
  end_date: "",
  location: "",
  expected_attendance: "",
  description: "",
};

/** Fields the server requires before an application can be *submitted*. */
const SUBMISSION_FIELDS: { key: keyof ApplicationWrite; label: string }[] = [
  { key: "start_date", label: "Start date" },
  { key: "end_date", label: "End date" },
  { key: "location", label: "Location" },
  { key: "expected_attendance", label: "Expected attendance" },
];

function fromApplication(application: ApplicationWrite): FormState {
  return {
    event_name: application.event_name,
    event_type: application.event_type,
    start_date: toLocalInputValue(application.start_date),
    end_date: toLocalInputValue(application.end_date),
    location: application.location ?? "",
    // The input is a number field, so it holds a string; `null` becomes "".
    expected_attendance:
      application.expected_attendance === null ? "" : String(application.expected_attendance),
    description: application.description ?? "",
  };
}

/** Build the request payload, mapping "" and non-numbers to the API's nulls. */
function toPayload(state: FormState): ApplicationWrite {
  const attendance = state.expected_attendance.trim();
  const parsed = attendance === "" ? Number.NaN : Number(attendance);

  return {
    event_name: state.event_name.trim(),
    event_type: state.event_type,
    start_date: toApiTimestamp(state.start_date || null),
    end_date: toApiTimestamp(state.end_date || null),
    location: state.location.trim() || null,
    // `NaN` and negatives are both refused by the server's `ge=0`, so sending
    // null for a non-numeric value is the honest representation of "not set".
    expected_attendance: Number.isFinite(parsed) && parsed >= 0 ? Math.trunc(parsed) : null,
    description: state.description.trim() || null,
  };
}

export function ApplicationForm({ mode }: { mode: "create" | "edit" }) {
  const router = useRouter();
  const token = useToken();
  const toast = useToast();
  const params = useParams<{ id?: string }>();
  const applicationId = params.id;

  const isEdit = mode === "edit";

  // Fetch the existing application only when editing. On create the promise
  // resolves immediately so the same hook serves both modes.
  const existing = useApi<ApplicationWrite | undefined>(
    useCallback(
      (signal) =>
        isEdit && applicationId
          ? getApplication(applicationId, { token, signal })
          : Promise.resolve(undefined),
      [isEdit, applicationId, token],
    ),
    [isEdit, applicationId, token],
  );

  const [state, setState] = useState<FormState>(BLANK);
  const [seeded, setSeeded] = useState(false);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  /*
   * Seed the form once the fetched application arrives.
   *
   * This is the one legitimate effect-shaped problem in this screen: the values
   * come from a request, so they cannot be initial state. Guarded by `seeded` so a
   * background refresh cannot discard edits the user has already typed — losing a
   * typed permit application to an unrelated refetch would be unforgivable.
   */
  if (!seeded && existing.data && !existing.isRefreshing) {
    setState(fromApplication(existing.data));
    setSeeded(true);
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((current) => ({ ...current, [key]: value }));
    // Clearing the message as soon as the field is touched is what makes a form
    // feel responsive; leaving a stale error next to corrected input is worse
    // than no validation at all.
    setLocalErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  const save = useMutation(async (payload: ApplicationWrite) =>
    isEdit && applicationId
      ? updateApplication(applicationId, payload, { token })
      : createApplication(payload, { token }),
  );

  /* --- Local validation --------------------------------------------------- */

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};

    if (!state.event_name.trim()) {
      errors.event_name = "Give the event a name your city will recognise.";
    } else if (state.event_name.trim().length > 255) {
      errors.event_name = "Keep the name to 255 characters or fewer.";
    }

    if (state.start_date && state.end_date && state.end_date < state.start_date) {
      errors.end_date = "The end date cannot be before the start date.";
    }

    if (state.location.trim().length > 255) {
      errors.location = "Keep the location to 255 characters or fewer.";
    }

    const attendance = state.expected_attendance.trim();
    if (attendance !== "") {
      const parsed = Number(attendance);
      if (!Number.isFinite(parsed)) {
        errors.expected_attendance = "Attendance must be a whole number.";
      } else if (!Number.isInteger(parsed)) {
        errors.expected_attendance = "Attendance must be a whole number of people.";
      } else if (parsed < 0) {
        errors.expected_attendance = "Attendance cannot be negative.";
      }
    }

    return errors;
  }

  async function onSubmit() {
    const errors = validate();
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) {
      // Move focus to the first problem: a validation error the user has to hunt
      // for is a validation error they will ignore.
      const firstKey = Object.keys(errors)[0];
      document.getElementById(`application-${firstKey}`)?.focus();
      return;
    }

    const created = await save.run(toPayload(state));
    if (!created) return;

    toast.success(
      isEdit ? "Application saved" : "Draft created",
      isEdit
        ? "Your changes are recorded in the application history."
        : "Add the remaining details, then submit it for review when it is ready.",
    );
    router.push(`/applications/${created.id}`);
  }

  /* --- Derived ------------------------------------------------------------ */

  const attendanceNumber = useMemo(() => {
    const parsed = Number(state.expected_attendance.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }, [state.expected_attendance]);

  const triggersFireReview = attendanceNumber !== null && attendanceNumber > LARGE_EVENT_THRESHOLD;

  const missingForSubmission = useMemo(
    () =>
      SUBMISSION_FIELDS.filter((field) => {
        const value = state[field.key];
        return value === null || value === "";
      }),
    [state],
  );

  if (isEdit && existing.isLoading) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4">
        <div className="skeleton h-9 w-56 rounded-control" />
        <div className="skeleton h-40 rounded-card" />
      </div>
    );
  }

  // Merge server-reported field errors over the local ones: the server is the
  // authority, and its message is usually more specific than ours.
  const errors = { ...localErrors, ...(save.error?.fieldErrors ?? {}) };

  return (
    /*
     * A real `<form>` rather than a div with an onClick handler, so that pressing
     * Enter in any field submits. Screen readers also announce the group as a form,
     * and the submit button keeps its `type="submit"` semantics.
     */
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit();
      }}
      noValidate
      className="mx-auto w-full max-w-3xl space-y-6"
    >
      <div>
        <Link
          href={isEdit && applicationId ? `/applications/${applicationId}` : "/applications"}
          className="inline-flex items-center gap-1.5 rounded text-[13px] text-ink-500 transition-colors hover:text-ink-900"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          {isEdit ? "Back to application" : "Back to applications"}
        </Link>
      </div>

      {/*
        Only shown when the failure is not purely field-level. A 422 with a message
        per field is already rendered next to those fields, and repeating the whole
        summary above the form just makes the user read the same text twice.
      */}
      {save.error && Object.keys(save.error.fieldErrors).length === 0 && (
        <InlineError error={save.error} />
      )}

      <Panel
        title={isEdit ? "Application details" : "New application"}
        description={
          isEdit
            ? "Fields an agency has already been asked about can be changed here."
            : "Only the event name is required to save a draft. The rest can follow."
        }
      >
        <div className="space-y-5">
          <Field
            label="Event name"
            htmlFor="application-event_name"
            required
            error={errors.event_name}
            hint="How your city will refer to this event in correspondence."
          >
            <Input
              id="application-event_name"
              name="event_name"
              value={state.event_name}
              onChange={(event) => update("event_name", event.target.value)}
              invalid={Boolean(errors.event_name)}
              maxLength={255}
              placeholder="Riverside Half Marathon"
              disabled={save.isPending}
            />
          </Field>

          <Field
            label="Event type"
            htmlFor="application-event_type"
            required
            hint={
              <>
                Determines which agencies review this application.{" "}
                {eventTypeDescription(state.event_type)}.
              </>
            }
          >
            <Select
              value={state.event_type}
              onValueChange={(value) => update("event_type", value as EventType)}
              disabled={save.isPending}
            >
              <SelectTrigger id="application-event_type" aria-label="Event type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EVENT_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field
              label="Start date and time"
              htmlFor="application-start_date"
              error={errors.start_date}
              hint="Needed before the application can be submitted."
            >
              <Input
                id="application-start_date"
                name="start_date"
                type="datetime-local"
                value={state.start_date}
                onChange={(event) => update("start_date", event.target.value)}
                invalid={Boolean(errors.start_date)}
                disabled={save.isPending}
              />
            </Field>

            <Field
              label="End date and time"
              htmlFor="application-end_date"
              error={errors.end_date}
              hint="Single-day events can match the start."
            >
              <Input
                id="application-end_date"
                name="end_date"
                type="datetime-local"
                value={state.end_date}
                onChange={(event) => update("end_date", event.target.value)}
                invalid={Boolean(errors.end_date)}
                disabled={save.isPending}
              />
            </Field>
          </div>

          <Field
            label="Location"
            htmlFor="application-location"
            error={errors.location}
            hint="Address or meeting point for the event."
          >
            <Input
              id="application-location"
              name="location"
              leading={<MapPin />}
              value={state.location}
              onChange={(event) => update("location", event.target.value)}
              invalid={Boolean(errors.location)}
              maxLength={255}
              placeholder="Riverfront Park, North Gate"
              disabled={save.isPending}
            />
          </Field>

          <Field
            label="Expected attendance"
            htmlFor="application-expected_attendance"
            error={errors.expected_attendance}
            hint={
              triggersFireReview ? (
                <span className="flex items-start gap-1.5 text-attention-ink">
                  <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  Above {LARGE_EVENT_THRESHOLD.toLocaleString()}, the fire department is
                  added to the review automatically.
                </span>
              ) : (
                "Total number of people expected across the event."
              )
            }
          >
            <Input
              id="application-expected_attendance"
              name="expected_attendance"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              leading={<Users />}
              trailing="people"
              value={state.expected_attendance}
              onChange={(event) => update("expected_attendance", event.target.value)}
              invalid={Boolean(errors.expected_attendance)}
              placeholder="12000"
              disabled={save.isPending}
            />
          </Field>

          <Field
            label="Description"
            htmlFor="application-description"
            hint="What you are planning, the setup, and anything an agency will need to assess."
          >
            <Textarea
              id="application-description"
              name="description"
              rows={5}
              value={state.description}
              onChange={(event) => update("description", event.target.value)}
              placeholder="A half marathon on the riverside loop, starting at North Gate and finishing at the boathouse. Road closures from 06:00, medical cover provided by the event first-aid team."
              disabled={save.isPending}
            />
          </Field>
        </div>
      </Panel>

      {/* Submission readiness, stated plainly rather than discovered by a 422. */}
      <Panel
        title="Before you submit"
        description="An application can be saved as a draft at any time. Submitting requires these."
      >
        {missingForSubmission.length === 0 ? (
          <p className="flex items-start gap-2.5 text-sm text-positive-ink">
            <CalendarDays aria-hidden className="mt-0.5 size-4 shrink-0" />
            Everything the city needs is filled in. This application is ready to
            submit from its detail page.
          </p>
        ) : (
          <div className="space-y-3">
            <p className="text-[13px] text-ink-500">
              Still needed before this can go to agencies:
            </p>
            <ul className="flex flex-wrap gap-2">
              {missingForSubmission.map((field) => (
                <li
                  key={field.key}
                  className="rounded-full border border-attention/25 bg-attention-soft px-2.5 py-1 text-[13px] font-medium text-attention-ink"
                >
                  {field.label}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>

      <div className="flex flex-wrap items-center justify-end gap-2 pb-4">
        <Button
          variant="ghost"
          onClick={() =>
            router.push(isEdit && applicationId ? `/applications/${applicationId}` : "/applications")
          }
          disabled={save.isPending}
        >
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          {isEdit ? "Save changes" : "Save draft"}
        </Button>
      </div>
    </form>
  );
}