"use client";

import { Compass } from "lucide-react";
import { RequireRole } from "@/components/layout/guards";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth";
import { homePathForRole, rolePresentation } from "@/lib/status";

/**
 * The landing page for a role with no workspace.
 *
 * City Admin has no endpoints on the API — no admin routes exist at all — so
 * there is nothing truthful to render. Rather than build a dashboard of invented
 * numbers, this says what is true and offers the way out. A fabricated admin
 * console is the single easiest way to make an otherwise honest product feel
 * like a template.
 */
export function UnavailableState() {
  const { user, signOut } = useSession();

  const role = user ? rolePresentation(user.role) : null;

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-6 py-16">
      <div className="w-full max-w-lg text-center">
        <span className="mx-auto flex size-12 items-center justify-center rounded-full border border-line bg-surface">
          <Compass aria-hidden className="size-6 text-ink-400" />
        </span>

        <h1 className="mt-6 text-xl font-semibold tracking-tight text-ink-950">
          {role?.label ?? "Your"} workspace is not available yet
        </h1>

        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-ink-500">
          Your account is active and correctly signed in, but PermitFlow has no
          tools built for this role yet. City administration — configuring which
          agencies review which event types — is the next piece of work.
        </p>

        {user && (
          <p className="mt-4 text-[13px] text-ink-400">
            Signed in as <span className="text-ink-600">{user.email}</span>
          </p>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
          <Button variant="default" onClick={signOut}>
            Sign out
          </Button>
          {user && user.role !== "City Admin" && (
            <Button asChild variant="primary">
              <a href={homePathForRole(user.role)}>Go to my workspace</a>
            </Button>
          )}
        </div>

        <div className="mt-12 border-t border-line pt-8">
          <EmptyState
            icon={Compass}
            compact
            title="Nothing is hidden from you"
            description="This page is the honest answer: there is no admin tooling to show yet. No placeholder data has been invented to fill the gap."
          />
        </div>
      </div>
    </div>
  );
}

export default function UnavailablePage() {
  return (
    <RequireRole allow={["City Admin"]}>
      <UnavailableState />
    </RequireRole>
  );
}