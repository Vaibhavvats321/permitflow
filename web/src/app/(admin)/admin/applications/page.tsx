import type { Metadata } from "next";
import { AdminApplicationsList } from "./admin-applications-list";
import { PageBody, PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Applications" };

export default function AdminApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Every permit application in this city, across all organizers."
      />
      <PageBody>
        <AdminApplicationsList />
      </PageBody>
    </>
  );
}
