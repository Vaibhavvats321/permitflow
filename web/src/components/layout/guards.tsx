"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useSession } from "@/lib/auth";
import { homePathForRole, rolePresentation } from "@/lib/status";
import type { UserRole } from "@/lib/types";

/**
 * Route guards.
 *
 * These are a UX measure, not a security one. Authorization is enforced by the
 * API — a reviewer calling `/applications` gets a 403 regardless of what the
 * client does — so this exists to send someone to a screen that can actually
 * show them something, rather than to protect data.
 *
 * `RequireRole` renders nothing until the session has been validated. That is
 * deliberate: rendering on `isAuthenticated` alone would flash the login screen
 * for every signed-in user on every hard refresh, because `localStorage` is only
 * read in an effect.
 */

/** The gate spinner. Full-height so it does not appear mid-layout and jump. */
export function SessionLoading({ label = "Loading your workspace" }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-ink-500"
    >
      <Loader2 aria-hidden className="size-5 animate-spin text-ink-400" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

/** Requires a session; sends anonymous visitors to `/login`. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isReady, isAuthenticated } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (isReady && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return <SessionLoading />;
  return <>{children}</>;
}

/**
 * Requires one of the listed roles.
 *
 * A user in the right place but the wrong role is sent to their own workspace
 * rather than shown a 403: they typed or followed a link, and sending them
 * somewhere useful is a better answer than an error page for a route they were
 * never going to be able to use.
 */
export function RequireRole({
  allow,
  children,
}: {
  allow: readonly UserRole[];
  children: ReactNode;
}) {
  const { isReady, user } = useSession();
  const router = useRouter();

  const permitted = user ? allow.includes(user.role) : false;

  useEffect(() => {
    if (!isReady) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (!permitted) {
      router.replace(homePathForRole(user.role));
    }
  }, [isReady, user, permitted, router]);

  if (!isReady || !user || !permitted) return <SessionLoading />;
  return <>{children}</>;
}

/** Sends an already-signed-in user away from `/login`. */
export function RequireAnonymous({ children }: { children: ReactNode }) {
  const { isReady, user } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (isReady && user) {
      router.replace(homePathForRole(user.role));
    }
  }, [isReady, user, router]);

  if (!isReady || user) return <SessionLoading />;
  return <>{children}</>;
}

/**
 * Redirects to the role's own workspace.
 *
 * The root `/` is a marketing page, so this is for anything that has to be a
 * landing point without deciding who should see it — such as a post-login
 * navigation to a role-neutral path.
 */
export function RoleLanding() {
  const { isReady, user } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (isReady) {
      router.replace(user ? homePathForRole(user.role) : "/login");
    }
  }, [isReady, user, router]);

  return <SessionLoading label="Redirecting" />;
}

/**
 * A role-aware sentence for empty or informational screens.
 *
 * Exists so the wording about what a role can do lives with the role
 * definitions in `status.ts` instead of being retyped per screen.
 */
export function RoleNote({ role }: { role: UserRole | undefined }) {
  if (!role) return null;
  return <p className="text-sm text-ink-500">{rolePresentation(role).description}</p>;
}