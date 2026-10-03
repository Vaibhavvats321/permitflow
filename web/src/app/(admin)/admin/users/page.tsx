import type { Metadata } from "next";
import { AdminUsersList } from "./admin-users-list";
import { PageBody, PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Users" };

export default function AdminUsersPage() {
  return (
    <>
      <PageHeader
        title="Users"
        description="The organizer, reviewer and admin accounts that can sign in to this city."
      />
      <PageBody>
        <AdminUsersList />
      </PageBody>
    </>
  );
}
