"use client";

import { useState } from "react";
import { useToken } from "@/lib/auth";
import {
  createAdminAgency,
  deleteAdminAgency,
  updateAdminAgency,
} from "@/lib/endpoints";
import type { AgencyResponse, AgencyWrite } from "@/lib/types";
import { useMutation } from "@/lib/use-api";
import { ConfirmDialog } from "@/components/ui/dialog";
import { InlineError } from "@/components/ui/empty-state";
import { TextField } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/**
 * Create, edit and delete dialogs for the agency screens.
 *
 * Mounted only while open — the parent renders the dialog when there is an
 * agency (or an open flag) to act on — so every opening starts with fresh
 * state: the fields are seeded from the agency it was opened for, and a
 * stale server error from a previous attempt cannot linger.
 *
 * Failures stay inside the dialog rather than becoming a toast: a duplicate
 * name or a 409 from a referenced agency is something the user fixes right
 * here, and a message that disappears after four seconds is no help. The
 * server's message is shown verbatim — its 409 texts already name what has to
 * change.
 */

const MAX_NAME_LENGTH = 255;

/** Mirrors the server's `ge=0, le=2_000_000_000` on attendance_threshold. */
const MAX_THRESHOLD = 2_000_000_000;

function validateName(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return "Agency name is required.";
  if (trimmed.length > MAX_NAME_LENGTH) {
    return `Agency name must be ${MAX_NAME_LENGTH} characters or fewer.`;
  }
  return null;
}

/**
 * Empty means "no attendance rule" and is valid; anything else must be a
 * non-negative whole number within the server's range, so a bad value is
 * caught here instead of round-tripping to a 422.
 */
function validateThreshold(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (!/^\d+$/.test(trimmed)) {
    return "Attendance threshold must be a whole number of 0 or more.";
  }
  if (Number(trimmed) > MAX_THRESHOLD) {
    return `Attendance threshold must be ${MAX_THRESHOLD.toLocaleString()} or less.`;
  }
  return null;
}

/** "" -> null (clear); digits -> the number. Companion to validateThreshold. */
function parseThreshold(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed ? Number(trimmed) : null;
}

const THRESHOLD_HINT =
  "Expected attendance above this number adds the agency to the review automatically. Leave empty to require it only through routing rules.";

function ThresholdField({
  value,
  error,
  onChange,
  onEnter,
}: {
  value: string;
  error?: string;
  onChange: (next: string) => void;
  onEnter: () => void;
}) {
  return (
    <TextField
      label="Attendance threshold"
      hint={THRESHOLD_HINT}
      placeholder="e.g. 5000"
      value={value}
      inputMode="numeric"
      maxLength={10}
      error={error}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          onEnter();
        }
      }}
    />
  );
}

/* --- Create --------------------------------------------------------------- */

export function CreateAgencyDialog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState("");
  const [localError, setLocalError] = useState<{
    name?: string;
    threshold?: string;
  }>({});
  const create = useMutation((payload: AgencyWrite) =>
    createAdminAgency(payload, { token }),
  );

  const serverNameError = create.error?.isValidation
    ? create.error.fieldErrors.name
    : undefined;
  const serverThresholdError = create.error?.isValidation
    ? create.error.fieldErrors.attendance_threshold
    : undefined;
  const nameError = localError.name ?? serverNameError;
  const thresholdError = localError.threshold ?? serverThresholdError;
  const formError =
    serverNameError || serverThresholdError ? undefined : create.error;

  async function submit() {
    if (create.isPending) return;
    const nameProblem = validateName(name);
    const thresholdProblem = validateThreshold(threshold);
    if (nameProblem || thresholdProblem) {
      setLocalError({ name: nameProblem ?? undefined, threshold: thresholdProblem ?? undefined });
      return;
    }
    setLocalError({});
    const agency = await create.run({
      name: name.trim(),
      attendance_threshold: parseThreshold(threshold),
    });
    if (agency) {
      toast.success("Agency created", `${agency.name} can now be added to routing rules.`);
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
      title="Create an agency"
      confirmLabel="Create agency"
      loading={create.isPending}
      onConfirm={submit}
      description="Agencies review permit applications. The name must be unique in this city — it appears on every review the agency records."
    >
      <div className="space-y-3">
        <TextField
          label="Agency name"
          required
          autoFocus
          placeholder="e.g. Parks Department"
          value={name}
          maxLength={MAX_NAME_LENGTH}
          error={nameError ?? undefined}
          onChange={(event) => {
            setName(event.target.value);
            setLocalError((prev) => ({ ...prev, name: undefined }));
            if (create.error) create.reset();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <ThresholdField
          value={threshold}
          error={thresholdError}
          onChange={(next) => {
            setThreshold(next);
            setLocalError((prev) => ({ ...prev, threshold: undefined }));
            if (create.error) create.reset();
          }}
          onEnter={() => void submit()}
        />
        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Edit ----------------------------------------------------------------- */

export function EditAgencyDialog({
  agency,
  onClose,
  onDone,
}: {
  agency: AgencyResponse;
  onClose: () => void;
  onDone: (updated: AgencyResponse) => void;
}) {
  const token = useToken();
  const toast = useToast();
  const [name, setName] = useState(agency.name);
  const [threshold, setThreshold] = useState(
    agency.attendance_threshold == null ? "" : String(agency.attendance_threshold),
  );
  const [localError, setLocalError] = useState<{
    name?: string;
    threshold?: string;
  }>({});
  const save = useMutation((payload: AgencyWrite) =>
    updateAdminAgency(agency.id, payload, { token }),
  );

  const serverNameError = save.error?.isValidation
    ? save.error.fieldErrors.name
    : undefined;
  const serverThresholdError = save.error?.isValidation
    ? save.error.fieldErrors.attendance_threshold
    : undefined;
  const nameError = localError.name ?? serverNameError;
  const thresholdError = localError.threshold ?? serverThresholdError;
  const formError = serverNameError || serverThresholdError ? undefined : save.error;

  async function submit() {
    if (save.isPending) return;
    const nameProblem = validateName(name);
    const thresholdProblem = validateThreshold(threshold);
    if (nameProblem || thresholdProblem) {
      setLocalError({ name: nameProblem ?? undefined, threshold: thresholdProblem ?? undefined });
      return;
    }
    setLocalError({});
    // Both fields are always sent: what is on screen is exactly what is saved,
    // and an empty threshold box explicitly clears the rule (PATCH's null).
    const updated = await save.run({
      name: name.trim(),
      attendance_threshold: parseThreshold(threshold),
    });
    if (updated) {
      if (updated.name !== agency.name) {
        toast.success("Agency renamed", `Now listed as ${updated.name}.`);
      } else {
        toast.success(
          "Agency updated",
          updated.attendance_threshold == null
            ? `${updated.name} has no attendance rule; routing rules decide its reviews.`
            : `${updated.name} reviews events over ${updated.attendance_threshold.toLocaleString()} attendees.`,
        );
      }
      onDone(updated);
      onClose();
    }
  }

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title="Edit agency"
      confirmLabel="Save changes"
      loading={save.isPending}
      onConfirm={submit}
      description="Routing rules and review tasks reference the agency by id, so changes here only affect how it behaves and is displayed. The name must still be unique in this city."
    >
      <div className="space-y-3">
        <TextField
          label="Agency name"
          required
          autoFocus
          value={name}
          maxLength={MAX_NAME_LENGTH}
          error={nameError ?? undefined}
          onChange={(event) => {
            setName(event.target.value);
            setLocalError((prev) => ({ ...prev, name: undefined }));
            if (save.error) save.reset();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <ThresholdField
          value={threshold}
          error={thresholdError}
          onChange={(next) => {
            setThreshold(next);
            setLocalError((prev) => ({ ...prev, threshold: undefined }));
            if (save.error) save.reset();
          }}
          onEnter={() => void submit()}
        />
        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Delete --------------------------------------------------------------- */

export function DeleteAgencyDialog({
  agency,
  onClose,
  onDone,
}: {
  agency: AgencyResponse;
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const remove = useMutation(async () => {
    await deleteAdminAgency(agency.id, { token });
    return true;
  });

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={`Delete ${agency.name}?`}
      confirmLabel="Delete agency"
      tone="danger"
      loading={remove.isPending}
      onConfirm={async () => {
        const ok = await remove.run();
        if (ok) {
          toast.success("Agency deleted", `${agency.name} was removed from this city.`);
          onDone();
          onClose();
        }
      }}
      description={
        <>
          This permanently removes{" "}
          <span className="font-medium text-ink-800">{agency.name}</span> from this
          city. If routing rules or review tasks still reference the agency, the
          city refuses the deletion and the dialog says what to remove first.
        </>
      }
    >
      {remove.error && <InlineError error={remove.error} />}
    </ConfirmDialog>
  );
}
