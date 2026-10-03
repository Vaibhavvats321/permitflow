import type { Metadata } from "next";
import { AdminAgencyDetail } from "./admin-agency-detail";

export const metadata: Metadata = { title: "Agency" };

export default function AdminAgencyPage() {
  return <AdminAgencyDetail />;
}
