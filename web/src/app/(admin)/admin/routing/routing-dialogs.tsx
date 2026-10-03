"use client";

import { useCallback, useId, useState } from "react";
import type { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import {
  createAdminRoutingRule,
  deleteAdminRoutingRule,
  listAdminAgencies,
} from "@/lib/endpoints";
import { eventTypeDescription } from "@/lib/status";
import {
  EVENT_TYPES,
  type AgencyResponse,
  type EventType,
  type RoutingRule,
  type RoutingRuleCreate,
} from "@/lib/types";
import { useApi, useMutation } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { InlineError } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";

/**
 * Add/remove dialogs for the routing matrix.
 *
 * Mounted only while open, so every opening starts with fresh state. The
 * matrix cell that opened the dialog preselects its event type (and agency
 * for a pre-checked cell), but validation and the server both remain the
 * final word: the API answers a duplicate with 409, a bad event type with a
 * 422 that lists the accepted values, and an unknown agency with 404 — all
 * shown verbatim here rather than toasted.
 *
 * The POST schema is `extra="forbid"` with exactly two fields, so the create
 * payload never carries anything but `event_type` and `agency_id`. There is no
 * PATCH route: rules are only created or deleted.
 */

interface FieldErrors {
  event_type?: string;
  agency?: string;
}

/**
 * Split a failed mutation into a field message (a 422 that named `agency_id`)
 * and a form-level error for everything else — 409 duplicates, the string 422
 * for an invalid event type, 404s. Routing errors are string details in
 * practice; the field bucket exists because the schema types `agency_id` as a
 * UUID and a malformed one would arrive keyed.
 */
function splitServerError(error: ApiError | undefined): {
  fields: Record<string, string>;
  form: ApiError | undefined;
} {
  if (!error) return { fields: {}, form: undefined };
  const fields = error.isValidation ? error.fieldErrors : {};
  const hasKnownField = ["event_type", "agency_id"].some((key) => key in fields);
  if (error.isValidation && hasKnownField) return { fields, form: undefined };
  return { fields: {}, form: error };
}

/* --- Shared: agency select ------------------------------------------------ */

/**
 * Agency picker for the add dialog.
 *
 * Options already assigned to the selected event type are disabled with the
 * reason in their label — the practical duplicate prevention — while the
 * server's 409 remains the backstop. Its own component so the options request
 * fires only while a dialog is open, and the agency a matrix cell was
 * preselected from is synthesized in if it falls outside the fetched page.
 */
function AgencySelectField({
  value,
  onChange,
  error,
  disabledIds,
  preselected,
}: {
  value: string;
  onChange: (next: string) => void;
  error?: string;
  /** Agency ids already assigned to the selected event type. */
  disabledIds: Set<string>;
  /** The cell's agency, appended if the fetched page lacks it. */
  preselected?: { id: string; name: string };
}) {
  const token = useToken();
  const groupId = useId();

  const agencies = useApi<AgencyResponse[]>(
    useCallback(
      (signal) => listAdminAgencies({ limit: 100 }, { token, signal }),
      [token],
    ),
    [token],
  );

  const options: { id: string; name: string }[] = (agencies.data ?? []).map(
    (agency) => ({ id: agency.id, name: agency.name }),
  );
  if (preselected && !options.some((agency) => agency.id === preselected.id)) {
    options.push({ id: preselected.id, name: preselected.name });
  }

  const everyOptionDisabled =
    options.length > 0 && options.every((agency) => disabledIds.has(agency.id));

  return (
    <div className="space-y-1.5">
      <Field
        label="Agency"
        required
        htmlFor={groupId}
        error={error}
        hint={
          agencies.error
            ? undefined
            : agencies.isLoading
              ? "Loading agencies…"
              : everyOptionDisabled
                ? "Every agency is already assigned to this event type."
                : undefined
        }
      >
        <Select value={value} onValueChange={onChange} disabled={agencies.isLoading}>
          <SelectTrigger id={groupId} aria-label="Agency" invalid={Boolean(error)}>
            <SelectValue placeholder="Select an agency…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((agency) => {
              const taken = disabledIds.has(agency.id);
              return (
                <SelectItem key={agency.id} value={agency.id} disabled={taken}>
                  {agency.name}
                  {taken && " (already assigned)"}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </Field>
      {agencies.error && (
        <div className="flex items-center gap-2">
          <InlineError error={agencies.error} className="flex-1" />
          <Button variant="default" size="sm" onClick={agencies.reload}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}

/* --- Add ------------------------------------------------------------------ */

export function AddRoutingRuleDialog({
  initial,
  rules,
  onClose,
  onDone,
}: {
  /** What the opening cell already knew: a type, an agency, or both. */
  initial?: { event_type?: EventType; agency?: { id: string; name: string } };
  /** Current rules, to disable combinations that already exist. */
  rules: RoutingRule[];
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const eventTypeId = useId();

  const [eventType, setEventType] = useState<EventType | "">(initial?.event_type ?? "");
  const [agencyId, setAgencyId] = useState(initial?.agency?.id ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});

  const create = useMutation((payload: RoutingRuleCreate) =>
    createAdminRoutingRule(payload, { token }),
  );

  const { fields: serverFields, form: formError } = splitServerError(create.error);

  // Pairs that already exist for the currently selected event type.
  const assignedIds = new Set(
    eventType ? rules.filter((rule) => rule.event_type === eventType).map((rule) => rule.agency_id) : [],
  );

  function clearOnType(field: keyof FieldErrors) {
    setErrors((previous) => ({ ...previous, [field]: undefined }));
    if (create.error) create.reset();
  }

  async function submit() {
    if (create.isPending) return;

    const next: FieldErrors = {};
    if (!eventType) next.event_type = "Choose an event type.";
    if (!agencyId) {
      next.agency = "Choose an agency.";
    } else if (eventType && assignedIds.has(agencyId)) {
      next.agency = "This agency is already assigned to the selected event type.";
    }

    setErrors(next);
    // The `!eventType` check repeats so TypeScript narrows it for the payload.
    if (Object.keys(next).length > 0 || !eventType) return;

    const created = await create.run({ event_type: eventType, agency_id: agencyId });
    if (created) {
      toast.success(
        "Routing rule created",
        `${created.agency_name} will now review ${created.event_type} applications.`,
      );
      onDone();
      onClose();
    }
  }

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title="Add a routing rule"
      confirmLabel="Add rule"
      loading={create.isPending}
      onConfirm={submit}
      description="Assign an agency to review every application of the selected event type. The pair must be unique — an agency that already reviews the type is disabled below."
    >
      <div className="space-y-3">
        <Field
          label="Event type"
          required
          htmlFor={eventTypeId}
          error={errors.event_type ?? serverFields.event_type}
          hint={
            eventType
              ? `${eventTypeDescription(eventType)} — ${
                  rules.filter((rule) => rule.event_type === eventType).length
                } ${rules.filter((rule) => rule.event_type === eventType).length === 1 ? "agency" : "agencies"} assigned`
              : "The application type this rule applies to."
          }
        >
          <Select
            value={eventType}
            onValueChange={(next) => {
              setEventType(next as EventType);
              // The agency choice may no longer be valid for the new type.
              clearOnType("event_type");
              clearOnType("agency");
            }}
          >
            <SelectTrigger
              id={eventTypeId}
              aria-label="Event type"
              invalid={Boolean(errors.event_type ?? serverFields.event_type)}
            >
              <SelectValue placeholder="Select an event type…" />
            </SelectTrigger>
            <SelectContent>
              {EVENT_TYPES.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {eventType && (
          <AgencySelectField
            value={agencyId}
            onChange={(next) => {
              setAgencyId(next);
              clearOnType("agency");
            }}
            error={errors.agency ?? serverFields.agency_id}
            disabledIds={assignedIds}
            preselected={
              initial?.agency && initial.event_type === eventType
                ? initial.agency
                : undefined
            }
          />
        )}

        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Remove --------------------------------------------------------------- */

export function RemoveRoutingRuleDialog({
  rule,
  rules,
  onClose,
  onDone,
}: {
  rule: RoutingRule;
  /** All current rules, to spot when this is the event type's last agency. */
  rules: RoutingRule[];
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const remove = useMutation(async () => {
    await deleteAdminRoutingRule(rule.event_type, rule.agency_id, { token });
    return true;
  });

  const siblings = rules.filter(
    (other) => other.event_type === rule.event_type,
  ).length;
  const isLast = siblings <= 1;

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={`Remove ${rule.agency_name} from ${rule.event_type}?`}
      confirmLabel="Remove rule"
      tone="danger"
      loading={remove.isPending}
      onConfirm={async () => {
        const ok = await remove.run();
        if (ok) {
          toast.success(
            "Routing rule removed",
            `${rule.agency_name} no longer reviews ${rule.event_type} applications.`,
          );
          onDone();
          onClose();
        }
      }}
      description={
        <>
          New{" "}
          <span className="font-medium text-ink-800">{rule.event_type}</span>{" "}
          submissions will no longer require{" "}
          <span className="font-medium text-ink-800">{rule.agency_name}</span>
          ’s review. Review tasks already created are not changed.
          {isLast && (
            <>
              {" "}
              This is the last agency for {rule.event_type} — until another rule
              is added, submitting a {rule.event_type} application will be
              rejected.
            </>
          )}
        </>
      }
    >
      {remove.error && <InlineError error={remove.error} />}
    </ConfirmDialog>
  );
}
