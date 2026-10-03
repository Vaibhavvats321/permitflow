import { AppShell } from "@/components/layout/app-shell";
import { RequireRole } from "@/components/layout/guards";

/**
 * City Admin workspace. Same shell as the organizer and reviewer, different routes
 * and different nav items.
 */
export default function AdminLayout({ children }: LayoutProps<"/">) {
  return (
    <RequireRole allow={["City Admin"]}>
      <AppShell>{children}</AppShell>
    </RequireRole>
  );
}