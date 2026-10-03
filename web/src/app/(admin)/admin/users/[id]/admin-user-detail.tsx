"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useSession, useToken } from "@/lib/auth";
import { getAdminUser } from "@/lib/endpoints";
import { formatDate, formatRelative, shortId } from "@/lib/format";
import { rolePresentation } from "@/lib/status";
import type { AdminUserResponse } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DetailList, DetailRow, Panel } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { SkeletonText } from "@/components/ui/skeleton";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { DeleteUserDialog, EditUserDialog } from "../user-dialogs";

/**
 * One user, as the City Admin sees it.
 *
 * The detail endpoint is the source of truth — the page renders whatever it
 * returns and never merges in a row cached from the list. Edit updates the
 * page in place from the PATCH response; delete navigates back to the list
 * only on actual success.
 *
 * The admin's own account is editable but not deletable: the server always
 * refuses self-deletion (403), so the delete button is disabled with the
 * reason stated on the page rather than left to fail after a confirmation.
 */
export function AdminUserDetail() {
  const token = useToken();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const { user: sessionUser } = useSession();
  const userId = params.id;
  const isSelf = Boolean(sessionUser?.id && sessionUser.id === userId);

  const user = useApi<AdminUserResponse>(
    useCallback(
      (signal) => getAdminUser(userId, { token, signal }),
      [token, userId],
    ),
    [token, userId],
  );

  const { data, error, isLoading, reload, setData } = user;

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (isLoading) return <DetailSkeleton />;

  if (error) {
    return (
      <>
        <PageHeader
          title="User"
          crumbs={[
            { label: "Dashboard", href: "/admin-dashboard" },
            { label: "Users", href: "/admin/users" },
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
        <PageHeader title="User" />
        <PageBody>
          <ErrorState
            error={new ApiError(0, "The user could not be loaded.")}
            onRetry={reload}
          />
        </PageBody>
      </>
    );
  }

  const presentation = rolePresentation(data.role);

  return (
    <>
      <PageHeader
        title={data.email}
        crumbs={[
          { label: "Dashboard", href: "/admin-dashboard" },
          { label: "Users", href: "/admin/users" },
          { label: data.email },
        ]}
        actions={
          <>
            <Button variant="default" icon={<Pencil />} onClick={() => setEditOpen(true)}>
              Edit
            </Button>
            <Button
              variant="danger"
              icon={<Trash2 />}
              disabled={isSelf}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-500">
          <Badge size="sm">{presentation.label}</Badge>
          <span>Created {formatDate(data.created_at)}</span>
          <span aria-hidden className="text-ink-300">
            ·
          </span>
          <span className="tabular">{shortId(data.id)}</span>
        </div>
      </PageHeader>

      <PageBody>
        <div className="max-w-2xl space-y-5">
          <Panel title="User details" bodyClassName="px-5 pb-2 pt-1">
            <DetailList>
              <DetailRow label="Email">{data.email}</DetailRow>
              <DetailRow label="Role">
                <Badge size="sm">{presentation.label}</Badge>
                <span className="mt-1 block text-[13px] text-ink-500">
                  {presentation.description}
                </span>
              </DetailRow>
              <DetailRow label="Agency">
                {data.agency_name ??
                  (data.role === "Agency Reviewer" ? "Not set" : "Not applicable")}
              </DetailRow>
              <DetailRow label="User ID">
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

          <div className="space-y-3 px-1">
            <p className="text-[13px] leading-relaxed text-ink-400">
              Role is fixed at creation — the server has no role-change field, so
              this page does not offer one. An agency can be moved from the edit
              dialog but never cleared, and the password changes only when you
              type a new one.
            </p>
            <p className="text-[13px] leading-relaxed text-ink-400">
              Deletion removes the login only. When this account has recorded
              audit events the server refuses — the audit trail is never
              deleted — and the confirmation dialog says so.
              {isSelf && (
                <>
                  {" "}
                  You are signed in as this account, and the server never allows
                  deleting your own account, so Delete is unavailable here.
                </>
              )}
            </p>
          </div>
        </div>
      </PageBody>

      {editOpen && (
        <EditUserDialog
          user={data}
          onClose={() => setEditOpen(false)}
          onDone={(updated) => setData(updated)}
        />
      )}

      {deleteOpen && !isSelf && (
        <DeleteUserDialog
          user={data}
          onClose={() => setDeleteOpen(false)}
          onDone={() => router.push("/admin/users")}
        />
      )}
    </>
  );
}

/* --- Skeleton ------------------------------------------------------------- */

function DetailSkeleton() {
  return (
    <>
      <PageHeader title="Loading user…" />
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
