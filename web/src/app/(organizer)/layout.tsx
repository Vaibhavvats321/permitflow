import { AppShell } from "@/components/layout/app-shell";
import { RequireRole } from "@/components/layout/guards";

/**
 * Organizer workspace.
 *
 * The shell and the role gate live here rather than on each page, so a new
 * organizer route is protected by default. A guard repeated per page is a guard
 * someone will forget to add.
 */
export default function OrganizerLayout({ children }: LayoutProps<"/">) {
  return (
    <RequireRole allow={["Organizer"]}>
      <AppShell>{children}</AppShell>
    </RequireRole>
  );
}