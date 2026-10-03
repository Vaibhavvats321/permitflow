import type { Metadata } from "next";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { ApplicationForm } from "@/components/applications/application-form";

export const metadata: Metadata = { title: "Edit application" };

export default function EditApplicationPage() {
  return (
    <>
      <PageHeader
        title="Edit application"
        description="Corrections you make here are recorded in the application's history."
      />
      <PageBody>
        <ApplicationForm mode="edit" />
      </PageBody>
    </>
  );
}