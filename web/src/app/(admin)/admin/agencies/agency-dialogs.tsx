"use client";

import { useState } from "react";
import { useToken } from "@/lib/auth";
import {
  createAdminAgency,
  deleteAdminAgency,
  updateAdminAgency,
} from "@/lib/endpoints";
import type { AgencyResponse } from "@/lib/types";
import { useMutation } from "@/lib/use-api";
import { ConfirmDialog } from "@/components/ui/dialog";
import { InlineError } from "@/components/ui/empty-state";
import { TextField } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/**
 * Create, rename and delete dialogs for the agency screens.
 *
 * Mounted only while open — the parent renders the dialog when there is an
 * agency (or an open flag) to act on — so every opening starts with fresh
 * state: the rename field is seeded from the agency it was opened for, and a
 * stale server error from a previous attempt cannot linger.
 *
 * Failures stay inside the dialog rather than becoming a toast: a duplicate
 * name or a 409 from a referenced agency is something the user fixes right
 * here, and a message that disappears after four seconds is no help. The
 * server's message is shown verbatim — its 409 texts already name what has to
 * change.
 */

const MAX_NAME_LENGTH = 255;

function validateName(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return "Agency name is required.";
  if (trimmed.length > MAX_NAME_LENGTH) {
    return `Agency name must be ${MAX_NAME_LENGTH} characters or fewer.`;
  }
  return null;
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
  const [localError, setLocalError] = useState<string | null>(null);
  const create = useMutation((trimmed: string) =>
    createAdminAgency({ name: trimmed }, { token }),
  );

  const serverFieldError = create.error?.isValidation
    ? create.error.fieldErrors.name
    : undefined;
  const fieldError = localError ?? serverFieldError;
  const formError = serverFieldError ? undefined : create.error;

  async function submit() {
    if (create.isPending) return;
    const invalid = validateName(name);
    if (invalid) {
      setLocalError(invalid);
      return;
    }
    setLocalError(null);
    const agency = await create.run(name.trim());
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
          error={fieldError ?? undefined}
          onChange={(event) => {
            setName(event.target.value);
            setLocalError(null);
            if (create.error) create.reset();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />
        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Rename --------------------------------------------------------------- */

export function RenameAgencyDialog({
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
  const [localError, setLocalError] = useState<string | null>(null);
  const rename = useMutation((trimmed: string) =>
    updateAdminAgency(agency.id, { name: trimmed }, { token }),
  );

  const serverFieldError = rename.error?.isValidation
    ? rename.error.fieldErrors.name
    : undefined;
  const fieldError = localError ?? serverFieldError;
  const formError = serverFieldError ? undefined : rename.error;

  async function submit() {
    if (rename.isPending) return;
    const invalid = validateName(name);
    if (invalid) {
      setLocalError(invalid);
      return;
    }
    setLocalError(null);
    const updated = await rename.run(name.trim());
    if (updated) {
      toast.success("Agency renamed", `Now listed as ${updated.name}.`);
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
      title="Rename agency"
      confirmLabel="Save name"
      loading={rename.isPending}
      onConfirm={submit}
      description="Routing rules and review tasks reference the agency by id, so renaming only changes how it is displayed. The new name must still be unique in this city."
    >
      <div className="space-y-3">
        <TextField
          label="Agency name"
          required
          autoFocus
          value={name}
          maxLength={MAX_NAME_LENGTH}
          error={fieldError ?? undefined}
          onChange={(event) => {
            setName(event.target.value);
            setLocalError(null);
            if (rename.error) rename.reset();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
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
