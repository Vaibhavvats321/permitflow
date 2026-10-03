import { AppShell } from "@/components/layout/app-shell";
import { RequireRole } from "@/components/layout/guards";

/**
 * Agency reviewer workspace. Same shell as the organizer, different routes and
 * different nav items.
 */
export default function ReviewerLayout({ children }: LayoutProps<"/">) {
  return (
    <RequireRole allow={["Agency Reviewer"]}>
      <AppShell>{children}</AppShell>
    </RequireRole>
  );
}