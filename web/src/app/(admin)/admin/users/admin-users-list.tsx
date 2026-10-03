"use client";

import { Pencil, Plus, Trash2, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useSession, useToken } from "@/lib/auth";
import { PageSize } from "@/lib/constants";
import { listAdminUsers } from "@/lib/endpoints";
import { formatDate, shortId } from "@/lib/format";
import { rolePresentation } from "@/lib/status";
import type { AdminUserResponse } from "@/lib/types";
import { usePaginatedApi } from "@/lib/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeadCell,
  TableRow,
} from "@/components/ui/table";
import { CreateUserDialog, DeleteUserDialog, EditUserDialog } from "./user-dialogs";

/**
 * The City Admin's user list.
 *
 * Rows link to the user's detail view; edit and delete open dialogs that talk
 * to the admin user endpoints directly. The list only refreshes after a
 * confirmed success, so a refused deletion — a user who authored audit events,
 * or the signed-in admin's own account — leaves the row exactly where it was
 * rather than pretending it is gone.
 *
 * The signed-in admin's own row never offers delete: the server always
 * refuses self-deletion (403), and an action that cannot ever succeed is worse
 * than no action.
 */
export function AdminUsersList() {
  const token = useToken();
  const { user: sessionUser } = useSession();
  const selfId = sessionUser?.id;

  const {
    items: users,
    error,
    isLoading,
    isRefreshing,
    isLoadingMore,
    mayHaveMore,
    loadMore,
    reload,
  } = usePaginatedApi<AdminUserResponse>(
    useCallback(
      (signal, offset, limit) =>
        listAdminUsers({ offset, limit }, { token, signal }),
      [token],
    ),
    PageSize,
    [token],
    (user) => user.id,
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<AdminUserResponse | null>(null);
  const [deleting, setDeleting] = useState<AdminUserResponse | null>(null);

  if (error) {
    return (
      <Panel bodyClassName="p-0">
        <ErrorState error={error} onRetry={reload} />
      </Panel>
    );
  }

  const isFirstLoad = isLoading;

  return (
    <>
      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <p className="text-[13px] text-ink-500">
            {isFirstLoad ? (
              "Loading users…"
            ) : (
              <>
                Showing{" "}
                <span className="tabular font-medium text-ink-800">
                  {users.length}
                </span>{" "}
                {users.length === 1 ? "user" : "users"}
                {mayHaveMore && " · more available"}
                {isRefreshing && " · refreshing…"}
              </>
            )}
          </p>
          <Button
            variant="primary"
            icon={<Plus />}
            disabled={isFirstLoad}
            onClick={() => setCreateOpen(true)}
          >
            Create user
          </Button>
        </div>

        {isFirstLoad ? (
          <SkeletonRows rows={5} columns={5} />
        ) : users.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No users in this city yet"
            description="Create the organizer, reviewer and admin accounts for this city. Agency reviewers are assigned to an agency; organizers and admins are city-wide."
            action={
              <Button variant="primary" icon={<Plus />} onClick={() => setCreateOpen(true)}>
                Create user
              </Button>
            }
          />
        ) : (
          <>
            <UserTable
              users={users}
              selfId={selfId}
              onEdit={setEditing}
              onDelete={setDeleting}
            />

            {mayHaveMore && (
              <div className="flex flex-col items-center gap-2 border-t border-line p-4">
                <Button
                  variant="default"
                  loading={isLoadingMore}
                  onClick={loadMore}
                >
                  Load more users
                </Button>
                <p className="text-[12px] text-ink-400">
                  {users.length} loaded so far
                </p>
              </div>
            )}
          </>
        )}
      </Panel>

      {createOpen && (
        <CreateUserDialog
          onClose={() => setCreateOpen(false)}
          onDone={reload}
        />
      )}

      {editing && (
        <EditUserDialog
          user={editing}
          onClose={() => setEditing(null)}
          onDone={reload}
        />
      )}

      {deleting && (
        <DeleteUserDialog
          user={deleting}
          onClose={() => setDeleting(null)}
          onDone={reload}
        />
      )}
    </>
  );
}

/* --- Table ---------------------------------------------------------------- */

function UserTable({
  users,
  selfId,
  onEdit,
  onDelete,
}: {
  users: AdminUserResponse[];
  selfId: string | undefined;
  onEdit: (user: AdminUserResponse) => void;
  onDelete: (user: AdminUserResponse) => void;
}) {
  return (
    <>
      {/* Table from `md` up. */}
      <div className="hidden md:block">
        <Table>
          <caption className="sr-only">Users in this city</caption>
          <TableHead>
            <TableRow className="hover:bg-transparent">
              <TableHeadCell>User</TableHeadCell>
              <TableHeadCell>Role</TableHeadCell>
              <TableHeadCell>Agency</TableHeadCell>
              <TableHeadCell>Created</TableHeadCell>
              <TableHeadCell>
                <span className="sr-only">Actions</span>
              </TableHeadCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                selfId={selfId}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Cards below `md`. The same data, laid out for a narrow viewport. */}
      <ul className="divide-y divide-line md:hidden">
        {users.map((user) => (
          <li key={user.id} className="px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <Link
                  href={`/admin/users/${user.id}`}
                  className="block truncate text-sm font-medium text-ink-900 hover:text-brand-700"
                >
                  {user.email}
                </Link>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-500">
                  <Badge size="sm">{rolePresentation(user.role).label}</Badge>
                  {user.agency_name && <span>{user.agency_name}</span>}
                </div>
                <p className="mt-1 text-[12px] text-ink-500">
                  <span className="tabular">{shortId(user.id)}</span>
                  <span aria-hidden className="mx-1.5">
                    ·
                  </span>
                  Created {formatDate(user.created_at)}
                </p>
              </div>
              <RowActions
                user={user}
                selfId={selfId}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function UserRow({
  user,
  selfId,
  onEdit,
  onDelete,
}: {
  user: AdminUserResponse;
  selfId: string | undefined;
  onEdit: (user: AdminUserResponse) => void;
  onDelete: (user: AdminUserResponse) => void;
}) {
  return (
    <TableRow className="group">
      <TableCell>
        <Link
          href={`/admin/users/${user.id}`}
          className="block max-w-[24rem] focus-visible:outline-none"
        >
          <span className="block truncate text-[13px] font-medium text-ink-900 transition-colors group-hover:text-brand-700">
            {user.email}
          </span>
          <span className="mt-0.5 block text-[12px] tabular text-ink-400">
            {shortId(user.id)}
          </span>
        </Link>
      </TableCell>
      <TableCell>
        <Badge size="sm">{rolePresentation(user.role).label}</Badge>
      </TableCell>
      <TableCell>
        <span className="text-[13px] text-ink-600">
          {user.agency_name ??
            (user.role === "Agency Reviewer" ? "Not set" : "—")}
        </span>
      </TableCell>
      <TableCell>
        <span className="whitespace-nowrap text-[13px] text-ink-500">
          {formatDate(user.created_at)}
        </span>
      </TableCell>
      <TableCell>
        <RowActions user={user} selfId={selfId} onEdit={onEdit} onDelete={onDelete} />
      </TableCell>
    </TableRow>
  );
}

function RowActions({
  user,
  selfId,
  onEdit,
  onDelete,
}: {
  user: AdminUserResponse;
  selfId: string | undefined;
  onEdit: (user: AdminUserResponse) => void;
  onDelete: (user: AdminUserResponse) => void;
}) {
  const isSelf = Boolean(selfId && user.id === selfId);

  return (
    <div className="flex items-center justify-end gap-1.5">
      <Button
        variant="ghost"
        size="sm"
        icon={<Pencil aria-hidden />}
        className="text-ink-500 hover:text-ink-800"
        aria-label={`Edit ${user.email}`}
        onClick={() => onEdit(user)}
      >
        Edit
      </Button>
      {!isSelf && (
        <Button
          variant="ghost"
          size="sm"
          icon={<Trash2 aria-hidden />}
          className="text-critical hover:bg-critical-soft hover:text-critical-ink"
          aria-label={`Delete ${user.email}`}
          onClick={() => onDelete(user)}
        >
          Delete
        </Button>
      )}
    </div>
  );
}
