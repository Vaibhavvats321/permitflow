import type { Metadata } from "next";
import { AdminAgenciesList } from "./admin-agencies-list";
import { PageBody, PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Agencies" };

export default function AdminAgenciesPage() {
  return (
    <>
      <PageHeader
        title="Agencies"
        description="The departments in this city that review permit applications."
      />
      <PageBody>
        <AdminAgenciesList />
      </PageBody>
    </>
  );
}
