"use client";

import type { ReactNode } from "react";
import { Logo } from "./logo";
import { TooltipProvider } from "@/components/ui/primitives";
import { Sidebar, MobileNav } from "./sidebar";

/**
 * The authenticated application shell: sidebar, content column.
 *
 * Shared by the organizer and reviewer workspaces rather than duplicated, so the
 * chrome cannot drift between roles. What differs — the nav items — is decided by
 * the sidebar from the session's role.
 *
 * Deliberately not sticky at the top: the sidebar scrolls with the content. On a
 * laptop the viewport is short, and a pinned sidebar would eat the vertical space
 * an audit timeline needs.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={250} skipDelayDuration={300}>
      <div className="flex min-h-dvh bg-canvas">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          {/* The top bar exists only below `lg`; the sidebar covers the rest. */}
          <div className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4 lg:hidden">
            <MobileNav />
            <Logo className="size-6" />
            <span className="text-[15px] font-semibold tracking-tight text-ink-900">
              PermitFlow
            </span>
          </div>
          <main className="flex-1">{children}</main>
        </div>
      </div>
    </TooltipProvider>
  );
}