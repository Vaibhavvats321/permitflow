"use client";

import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { useToken } from "@/lib/auth";
import { PageSize } from "@/lib/constants";
import { listAdminAgencies } from "@/lib/endpoints";
import { formatDate, shortId } from "@/lib/format";
import type { AgencyResponse } from "@/lib/types";
import { usePaginatedApi } from "@/lib/use-api";
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
import {
  CreateAgencyDialog,
  DeleteAgencyDialog,
  EditAgencyDialog,
} from "./agency-dialogs";

/**
 * The City Admin's agency list.
 *
 * Read-plus-mutate: rows link to the agency's detail view, and the edit and
 * delete actions open dialogs that talk to the admin agency endpoints directly.
 * The list only refreshes after a confirmed success, so a refused deletion
 * leaves the row exactly where it was rather than pretending it is gone.
 */
export function AdminAgenciesList() {
  const token = useToken();

  const {
    items: agencies,
    error,
    isLoading,
    isRefreshing,
    isLoadingMore,
    mayHaveMore,
    loadMore,
    reload,
  } = usePaginatedApi<AgencyResponse>(
    useCallback(
      (signal, offset, limit) =>
        listAdminAgencies({ offset, limit }, { token, signal }),
      [token],
    ),
    PageSize,
    [token],
    (agency) => agency.id,
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<AgencyResponse | null>(null);
  const [deleting, setDeleting] = useState<AgencyResponse | null>(null);

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
        {/* Toolbar: the count states what is on screen rather than implying a
            total, and the create action sits where the eye lands after it. */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <p className="text-[13px] text-ink-500">
            {isFirstLoad ? (
              "Loading agencies…"
            ) : (
              <>
                Showing{" "}
                <span className="tabular font-medium text-ink-800">
                  {agencies.length}
                </span>{" "}
                {agencies.length === 1 ? "agency" : "agencies"}
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
            Create agency
          </Button>
        </div>

        {isFirstLoad ? (
          <SkeletonRows rows={5} columns={4} />
        ) : agencies.length === 0 ? (
          <EmptyState
            icon={Building2}
            title="No agencies in this city yet"
            description="Create the departments that will review permit applications — Police, Fire, Health and so on. Routing rules can point at an agency once it exists."
            action={
              <Button variant="primary" icon={<Plus />} onClick={() => setCreateOpen(true)}>
                Create agency
              </Button>
            }
          />
        ) : (
          <>
            <AgencyTable
              agencies={agencies}
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
                  Load more agencies
                </Button>
                <p className="text-[12px] text-ink-400">
                  {agencies.length} loaded so far
                </p>
              </div>
            )}
          </>
        )}
      </Panel>

      {createOpen && (
        <CreateAgencyDialog
          onClose={() => setCreateOpen(false)}
          onDone={reload}
        />
      )}

      {editing && (
        <EditAgencyDialog
          agency={editing}
          onClose={() => setEditing(null)}
          onDone={reload}
        />
      )}

      {deleting && (
        <DeleteAgencyDialog
          agency={deleting}
          onClose={() => setDeleting(null)}
          onDone={reload}
        />
      )}
    </>
  );
}

/* --- Table ---------------------------------------------------------------- */

function AgencyTable({
  agencies,
  onEdit,
  onDelete,
}: {
  agencies: AgencyResponse[];
  onEdit: (agency: AgencyResponse) => void;
  onDelete: (agency: AgencyResponse) => void;
}) {
  return (
    <>
      {/* Table from `md` up. */}
      <div className="hidden md:block">
        <Table>
          <caption className="sr-only">Agencies in this city</caption>
          <TableHead>
            <TableRow className="hover:bg-transparent">
              <TableHeadCell>Agency</TableHeadCell>
              <TableHeadCell>Attendance threshold</TableHeadCell>
              <TableHeadCell>Created</TableHeadCell>
              <TableHeadCell>
                <span className="sr-only">Actions</span>
              </TableHeadCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {agencies.map((agency) => (
              <AgencyRow
                key={agency.id}
                agency={agency}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Cards below `md`. The same data, laid out for a narrow viewport. */}
      <ul className="divide-y divide-line md:hidden">
        {agencies.map((agency) => (
          <li key={agency.id} className="px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink-900">
                  {agency.name}
                </p>
                <p className="mt-1 text-[12px] text-ink-500">
                  <span className="tabular">{shortId(agency.id)}</span>
                  <span aria-hidden className="mx-1.5">
                    ·
                  </span>
                  {agency.attendance_threshold == null
                    ? "No attendance rule"
                    : `Over ${agency.attendance_threshold.toLocaleString()} attendees`}
                  <span aria-hidden className="mx-1.5">
                    ·
                  </span>
                  Created {formatDate(agency.created_at)}
                </p>
              </div>
              <RowActions agency={agency} onEdit={onEdit} onDelete={onDelete} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function AgencyRow({
  agency,
  onEdit,
  onDelete,
}: {
  agency: AgencyResponse;
  onEdit: (agency: AgencyResponse) => void;
  onDelete: (agency: AgencyResponse) => void;
}) {
  return (
    <TableRow className="group">
      <TableCell>
        <span className="block max-w-[24rem] truncate text-[13px] font-medium text-ink-900">
          {agency.name}
        </span>
        <span className="mt-0.5 block text-[12px] tabular text-ink-400">
          {shortId(agency.id)}
        </span>
      </TableCell>
      <TableCell>
        {/* "—" means no attendance rule at all: the agency joins only through
            routing rules. Anything else is a strictly-greater-than value. */}
        <span className="whitespace-nowrap text-[13px] text-ink-500">
          {agency.attendance_threshold == null
            ? "—"
            : `Over ${agency.attendance_threshold.toLocaleString()}`}
        </span>
      </TableCell>
      <TableCell>
        <span className="whitespace-nowrap text-[13px] text-ink-500">
          {formatDate(agency.created_at)}
        </span>
      </TableCell>
      <TableCell>
        <RowActions agency={agency} onEdit={onEdit} onDelete={onDelete} />
      </TableCell>
    </TableRow>
  );
}

function RowActions({
  agency,
  onEdit,
  onDelete,
}: {
  agency: AgencyResponse;
  onEdit: (agency: AgencyResponse) => void;
  onDelete: (agency: AgencyResponse) => void;
}) {
  return (
    <div className="flex items-center justify-end gap-1.5">
      <Button
        variant="ghost"
        size="sm"
        icon={<Pencil aria-hidden />}
        className="text-ink-500 hover:text-ink-800"
        aria-label={`Edit ${agency.name}`}
        onClick={() => onEdit(agency)}
      >
        Edit
      </Button>
      <Button
        variant="ghost"
        size="sm"
        icon={<Trash2 aria-hidden />}
        className="text-critical hover:bg-critical-soft hover:text-critical-ink"
        aria-label={`Delete ${agency.name}`}
        onClick={() => onDelete(agency)}
      >
        Delete
      </Button>
    </div>
  );
}
