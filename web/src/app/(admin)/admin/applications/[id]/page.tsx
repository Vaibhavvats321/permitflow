import type { Metadata } from "next";
import { AdminApplicationDetail } from "./admin-application-detail";

export const metadata: Metadata = { title: "Application" };

export default function AdminApplicationPage() {
  return <AdminApplicationDetail />;
}
