"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useToken } from "@/lib/auth";
import { getAdminAgency } from "@/lib/endpoints";
import { formatDate, formatRelative, shortId } from "@/lib/format";
import type { AgencyResponse } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { DetailList, DetailRow, Panel } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { SkeletonText } from "@/components/ui/skeleton";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { DeleteAgencyDialog, EditAgencyDialog } from "../agency-dialogs";

/**
 * One agency, as the City Admin sees it.
 *
 * The detail endpoint is the source of truth — the page renders whatever it
 * returns and never merges in a row cached from the list, so an edit done
 * elsewhere cannot be masked here. Edit updates the page in place from the
 * PATCH response; delete navigates back to the list only on actual success.
 */
export function AdminAgencyDetail() {
  const token = useToken();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const agencyId = params.id;

  const agency = useApi<AgencyResponse>(
    useCallback(
      (signal) => getAdminAgency(agencyId, { token, signal }),
      [token, agencyId],
    ),
    [token, agencyId],
  );

  const { data, error, isLoading, reload, setData } = agency;

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (isLoading) return <DetailSkeleton />;

  if (error) {
    return (
      <>
        <PageHeader
          title="Agency"
          crumbs={[
            { label: "Dashboard", href: "/admin-dashboard" },
            { label: "Agencies", href: "/admin/agencies" },
            { label: "Not found" },
          ]}
        />
        <PageBody>
          <ErrorState error={error} onRetry={reload} />
        </PageBody>
      </>
    );
  }

  // See the application detail page: neither loading, nor error, nor data is a
  // hook bug, so it fails here rather than rendering a screen of `undefined`.
  if (!data) {
    return (
      <>
        <PageHeader title="Agency" />
        <PageBody>
          <ErrorState
            error={new ApiError(0, "The agency could not be loaded.")}
            onRetry={reload}
          />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={data.name}
        crumbs={[
          { label: "Dashboard", href: "/admin-dashboard" },
          { label: "Agencies", href: "/admin/agencies" },
          { label: data.name },
        ]}
        actions={
          <>
            <Button variant="default" icon={<Pencil />} onClick={() => setEditOpen(true)}>
              Edit
            </Button>
            <Button variant="danger" icon={<Trash2 />} onClick={() => setDeleteOpen(true)}>
              Delete
            </Button>
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-500">
          <span>Created {formatDate(data.created_at)}</span>
          <span aria-hidden className="text-ink-300">
            ·
          </span>
          <span className="tabular">{shortId(data.id)}</span>
        </div>
      </PageHeader>

      <PageBody>
        <div className="max-w-2xl space-y-5">
          <Panel title="Agency details" bodyClassName="px-5 pb-2 pt-1">
            <DetailList>
              <DetailRow label="Name">{data.name}</DetailRow>
              <DetailRow label="Attendance threshold">
                {data.attendance_threshold == null ? (
                  <span className="text-ink-400">
                    None — required only by routing rules
                  </span>
                ) : (
                  <span className="tabular">
                    Over {data.attendance_threshold.toLocaleString()} attendees
                  </span>
                )}
              </DetailRow>
              <DetailRow label="Agency ID">
                <code className="break-all text-[13px] text-ink-600">{data.id}</code>
              </DetailRow>
              <DetailRow label="Created">
                <span className="tabular">{formatDate(data.created_at)}</span>
                <span className="mt-0.5 block text-[13px] text-ink-500">
                  {formatRelative(data.created_at)}
                </span>
              </DetailRow>
            </DetailList>
          </Panel>

          <p className="px-1 text-[13px] leading-relaxed text-ink-400">
            Routing rules and review tasks reference this agency. The city refuses
            to delete an agency while any of them still point at it, and edits
            change only this agency — the next submission picks the change up.
          </p>
        </div>
      </PageBody>

      {editOpen && (
        <EditAgencyDialog
          agency={data}
          onClose={() => setEditOpen(false)}
          onDone={(updated) => setData(updated)}
        />
      )}

      {deleteOpen && (
        <DeleteAgencyDialog
          agency={data}
          onClose={() => setDeleteOpen(false)}
          onDone={() => router.push("/admin/agencies")}
        />
      )}
    </>
  );
}

/* --- Skeleton ------------------------------------------------------------- */

function DetailSkeleton() {
  return (
    <>
      <PageHeader title="Loading agency…" />
      <PageBody>
        <div className="max-w-2xl">
          <Panel>
            <SkeletonText lines={3} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
