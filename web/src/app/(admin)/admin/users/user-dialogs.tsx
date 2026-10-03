"use client";

import { useCallback, useId, useState } from "react";
import type { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import {
  createAdminUser,
  deleteAdminUser,
  listAdminAgencies,
  updateAdminUser,
} from "@/lib/endpoints";
import { shortId } from "@/lib/format";
import { rolePresentation } from "@/lib/status";
import {
  USER_ROLES,
  type AdminUserCreate,
  type AdminUserResponse,
  type AdminUserUpdate,
  type AgencyResponse,
  type UserRole,
} from "@/lib/types";
import { useApi, useMutation } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { InlineError } from "@/components/ui/empty-state";
import { Field, TextField } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";

/**
 * Create, edit and delete dialogs for the user screens.
 *
 * Mounted only while open, so every opening starts with fresh state: the edit
 * fields are seeded from the user it was opened for, and a stale server error
 * from a previous attempt cannot linger.
 *
 * What the API supports shapes what these dialogs offer:
 *
 * - Role is fixed at creation — `PATCH /admin/users/{id}` has no role field, so
 *   there is no role control in the edit dialog.
 * - `agency_id: null` is ignored server-side, so an agency can be moved but
 *   never cleared; the edit dialog only sends the agency when it actually
 *   changed, and never sends one for a non-reviewer role.
 * - Failures stay inside the dialog rather than becoming a toast: a duplicate
 *   email or a 409 about audit events is something the user resolves right
 *   here, and the server's message is shown verbatim.
 */

const MAX_EMAIL_LENGTH = 255;
const MIN_PASSWORD_LENGTH = 8;

function validateEmail(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return "Email is required.";
  if (trimmed.length > MAX_EMAIL_LENGTH) {
    return `Email must be ${MAX_EMAIL_LENGTH} characters or fewer.`;
  }
  // The server does not enforce a format beyond trim/lowercase/length, so the
  // client does not either — a stricter rule here would reject what the API
  // accepts and look like a bug.
  return null;
}

function validateNewPassword(raw: string): string | null {
  if (raw.trim().length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

interface FieldErrors {
  email?: string;
  password?: string;
  role?: string;
  agency?: string;
}

const SERVER_FIELD_KEYS = ["email", "password", "role", "agency_id"];

/**
 * Split a failed mutation into per-field messages (a 422 that named fields)
 * and a form-level error for anything else — 409 duplicates, string 422s,
 * 403s. A 422 whose fields are all unknown keys still surfaces as a form error
 * rather than disappearing between the two buckets.
 */
function splitServerError(error: ApiError | undefined): {
  fields: Record<string, string>;
  form: ApiError | undefined;
} {
  if (!error) return { fields: {}, form: undefined };
  const fields = error.isValidation ? error.fieldErrors : {};
  const hasKnownField = SERVER_FIELD_KEYS.some((key) => key in fields);
  if (error.isValidation && hasKnownField) return { fields, form: undefined };
  return { fields: {}, form: error };
}

/* --- Shared: agency select ------------------------------------------------ */

/**
 * The agency picker shown only for Agency Reviewers.
 *
 * Its own component so the options request fires only while it is mounted —
 * which is exactly when a reviewer role is in play — and so the current
 * agency can be synthesized into the list when it falls outside the first
 * page of results.
 */
function AgencySelectField({
  value,
  onChange,
  error,
  current,
}: {
  value: string;
  onChange: (next: string) => void;
  error?: string;
  /** The reviewer's present agency, appended if the fetched page lacks it. */
  current?: { id: string; name: string | null };
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

  // Only `id` and `name` are rendered, so the synthesized entry does not need
  // to fake the rest of an `AgencyResponse` (such as `created_at`).
  const options: { id: string; name: string }[] = (agencies.data ?? []).map(
    (agency) => ({ id: agency.id, name: agency.name }),
  );
  if (current && !options.some((agency) => agency.id === current.id)) {
    options.push({
      id: current.id,
      name: current.name ?? `Agency ${shortId(current.id)}`,
    });
  }

  const empty = agencies.data !== undefined && agencies.data.length === 0;

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
              : empty
                ? "No agencies exist yet — create one on the Agencies screen first."
                : undefined
        }
      >
        <Select
          value={value}
          onValueChange={onChange}
          disabled={agencies.isLoading}
        >
          <SelectTrigger id={groupId} aria-label="Agency" invalid={Boolean(error)}>
            <SelectValue placeholder="Select an agency…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((agency) => (
              <SelectItem key={agency.id} value={agency.id}>
                {agency.name}
              </SelectItem>
            ))}
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

/* --- Create --------------------------------------------------------------- */

export function CreateUserDialog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const roleId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole | "">("");
  const [agencyId, setAgencyId] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});

  const create = useMutation((payload: AdminUserCreate) =>
    createAdminUser(payload, { token }),
  );

  const { fields: serverFields, form: formError } = splitServerError(create.error);

  function clearOnType(field: keyof FieldErrors) {
    setErrors((previous) => ({ ...previous, [field]: undefined }));
    if (create.error) create.reset();
  }

  async function submit() {
    if (create.isPending) return;

    const next: FieldErrors = {};
    const emailProblem = validateEmail(email);
    if (emailProblem) next.email = emailProblem;
    const passwordProblem = validateNewPassword(password);
    if (passwordProblem) next.password = passwordProblem;
    if (!role) {
      next.role = "Choose a role.";
    } else if (role === "Agency Reviewer" && !agencyId) {
      next.agency = "Choose an agency for this reviewer.";
    }

    setErrors(next);
    // The `!role` check repeats so TypeScript narrows `role` to a real value
    // for the payload below.
    if (Object.keys(next).length > 0 || !role) return;

    const created = await create.run({
      email: email.trim(),
      password: password.trim(),
      role,
      // Only reviewers may carry an agency; sending one for any other role
      // would be a 422 from the server.
      ...(role === "Agency Reviewer" ? { agency_id: agencyId } : {}),
    });
    if (created) {
      toast.success("User created", `${created.email} can now sign in.`);
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
      title="Create a user"
      confirmLabel="Create user"
      loading={create.isPending}
      onConfirm={submit}
      description="New accounts sign in with their email and password. Agency reviewers must belong to an agency; organizers and admins must not."
    >
      <div className="space-y-3">
        <TextField
          label="Email"
          name="email"
          type="email"
          required
          autoFocus
          autoComplete="off"
          placeholder="e.g. reviewer@city.gov"
          value={email}
          maxLength={MAX_EMAIL_LENGTH}
          error={errors.email ?? serverFields.email}
          onChange={(event) => {
            setEmail(event.target.value);
            clearOnType("email");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />

        <TextField
          label="Password"
          name="password"
          type="password"
          required
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          maxLength={MAX_EMAIL_LENGTH}
          error={errors.password ?? serverFields.password}
          onChange={(event) => {
            setPassword(event.target.value);
            clearOnType("password");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />

        <Field
          label="Role"
          required
          htmlFor={roleId}
          error={errors.role ?? serverFields.role}
          hint={
            role
              ? rolePresentation(role).description
              : "What this account can do. The role is fixed once the user is created."
          }
        >
          <Select
            value={role}
            onValueChange={(next) => {
              setRole(next as UserRole);
              clearOnType("role");
            }}
          >
            <SelectTrigger id={roleId} aria-label="Role" invalid={Boolean(errors.role ?? serverFields.role)}>
              <SelectValue placeholder="Select a role…" />
            </SelectTrigger>
            <SelectContent>
              {USER_ROLES.map((value) => (
                <SelectItem key={value} value={value}>
                  {rolePresentation(value).label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {role === "Agency Reviewer" && (
          <AgencySelectField
            value={agencyId}
            onChange={(next) => {
              setAgencyId(next);
              clearOnType("agency");
            }}
            error={errors.agency ?? serverFields.agency_id}
          />
        )}

        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Edit ----------------------------------------------------------------- */

export function EditUserDialog({
  user,
  onClose,
  onDone,
}: {
  user: AdminUserResponse;
  onClose: () => void;
  onDone: (updated: AdminUserResponse) => void;
}) {
  const token = useToken();
  const toast = useToast();

  const [email, setEmail] = useState(user.email);
  const [password, setPassword] = useState("");
  const [agencyId, setAgencyId] = useState(user.agency_id ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});

  const save = useMutation((payload: AdminUserUpdate) =>
    updateAdminUser(user.id, payload, { token }),
  );

  const { fields: serverFields, form: formError } = splitServerError(save.error);

  function clearOnType(field: keyof FieldErrors) {
    setErrors((previous) => ({ ...previous, [field]: undefined }));
    if (save.error) save.reset();
  }

  async function submit() {
    if (save.isPending) return;

    const next: FieldErrors = {};
    const emailProblem = validateEmail(email);
    if (emailProblem) next.email = emailProblem;
    // Blank means "keep the current password", not "set an empty one".
    if (password.length > 0) {
      const passwordProblem = validateNewPassword(password);
      if (passwordProblem) next.password = passwordProblem;
    }
    if (user.role === "Agency Reviewer" && !agencyId) {
      next.agency = "Choose an agency for this reviewer.";
    }

    setErrors(next);
    if (Object.keys(next).length > 0) return;

    const payload: AdminUserUpdate = { email: email.trim() };
    if (password.length > 0) payload.password = password.trim();
    // The server only honours a non-null agency_id, and only for reviewers —
    // sending it unchanged would be a no-op anyway, and sending it for any
    // other role would be a 422.
    if (
      user.role === "Agency Reviewer" &&
      agencyId &&
      agencyId !== user.agency_id
    ) {
      payload.agency_id = agencyId;
    }

    const updated = await save.run(payload);
    if (updated) {
      toast.success("User updated", `${updated.email} was saved.`);
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
      title="Edit user"
      confirmLabel="Save changes"
      loading={save.isPending}
      onConfirm={submit}
      description="Change the sign-in email, reset the password, or move this reviewer to a different agency. The role itself cannot be changed — it is fixed when the account is created."
    >
      <div className="space-y-3">
        <TextField
          label="Email"
          name="email"
          type="email"
          required
          autoFocus
          autoComplete="off"
          value={email}
          maxLength={MAX_EMAIL_LENGTH}
          error={errors.email ?? serverFields.email}
          onChange={(event) => {
            setEmail(event.target.value);
            clearOnType("email");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />

        <TextField
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          placeholder="Leave blank to keep the current password"
          value={password}
          maxLength={MAX_EMAIL_LENGTH}
          hint="Leave blank to keep the current password."
          error={errors.password ?? serverFields.password}
          onChange={(event) => {
            setPassword(event.target.value);
            clearOnType("password");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit();
            }
          }}
        />

        <div className="rounded-control border border-line bg-surface-muted px-3 py-2.5">
          <p className="text-[13px] font-medium text-ink-700">Role</p>
          <p className="mt-0.5 text-[13px] text-ink-500">
            {rolePresentation(user.role).label} — fixed at creation. Role changes
            are not offered by the server.
          </p>
        </div>

        {user.role === "Agency Reviewer" && (
          <AgencySelectField
            value={agencyId}
            onChange={(next) => {
              setAgencyId(next);
              clearOnType("agency");
            }}
            error={errors.agency ?? serverFields.agency_id}
            current={
              user.agency_id
                ? { id: user.agency_id, name: user.agency_name }
                : undefined
            }
          />
        )}

        {formError && <InlineError error={formError} />}
      </div>
    </ConfirmDialog>
  );
}

/* --- Delete --------------------------------------------------------------- */

export function DeleteUserDialog({
  user,
  onClose,
  onDone,
}: {
  user: AdminUserResponse;
  onClose: () => void;
  onDone: () => void;
}) {
  const token = useToken();
  const toast = useToast();
  const remove = useMutation(async () => {
    await deleteAdminUser(user.id, { token });
    return true;
  });

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={`Delete ${user.email}?`}
      confirmLabel="Delete user"
      tone="danger"
      loading={remove.isPending}
      onConfirm={async () => {
        const ok = await remove.run();
        if (ok) {
          toast.success(
            "User deleted",
            `${user.email} no longer has a PermitFlow login.`,
          );
          onDone();
          onClose();
        }
      }}
      description={
        <>
          This permanently removes the login for{" "}
          <span className="font-medium text-ink-800">{user.email}</span>. The
          server refuses when this account has recorded audit events — the audit
          trail is never deleted — and the dialog will say why.
        </>
      }
    >
      {remove.error && <InlineError error={remove.error} />}
    </ConfirmDialog>
  );
}
