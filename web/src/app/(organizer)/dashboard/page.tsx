import type { Metadata } from "next";
import { OrganizerDashboard } from "./dashboard-content";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return <OrganizerDashboard />;
}