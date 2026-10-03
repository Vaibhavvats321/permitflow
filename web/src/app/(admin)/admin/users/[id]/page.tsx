import type { Metadata } from "next";
import { AdminUserDetail } from "./admin-user-detail";

export const metadata: Metadata = { title: "User" };

export default function AdminUserPage() {
  return <AdminUserDetail />;
}
