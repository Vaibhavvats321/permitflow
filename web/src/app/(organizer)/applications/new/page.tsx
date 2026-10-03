import type { Metadata } from "next";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { ApplicationForm } from "@/components/applications/application-form";

export const metadata: Metadata = { title: "New application" };

export default function NewApplicationPage() {
  return (
    <>
      <PageHeader
        title="New application"
        description="Start a draft for an event in your city."
      />
      <PageBody>
        <ApplicationForm mode="create" />
      </PageBody>
    </>
  );
}