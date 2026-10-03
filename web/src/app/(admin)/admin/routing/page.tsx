import type { Metadata } from "next";
import { AdminRoutingMatrix } from "./admin-routing-matrix";
import { PageBody, PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Routing" };

export default function AdminRoutingPage() {
  return (
    <>
      <PageHeader
        title="Routing"
        description="Which agencies review which event types. Changes apply to new submissions."
      />
      <PageBody>
        <AdminRoutingMatrix />
      </PageBody>
    </>
  );
}
