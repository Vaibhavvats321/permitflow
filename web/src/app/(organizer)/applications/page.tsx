import type { Metadata } from "next";
import Link from "next/link";
import { Plus } from "lucide-react";
import { ApplicationsList } from "./applications-list";
import { PageBody, PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Every permit application you have started or submitted."
        actions={
          <Button asChild variant="primary">
            <Link href="/applications/new">
              <Plus aria-hidden />
              New application
            </Link>
          </Button>
        }
      />
      <PageBody>
        <ApplicationsList />
      </PageBody>
    </>
  );
}