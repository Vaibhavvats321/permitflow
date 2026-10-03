"use client";

import {
  Building2,
  CheckCircle2,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Route,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { rolePresentation } from "@/lib/status";
import { Avatar, AvatarFallback, initialFromEmail } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { Logo } from "./logo";

/**
 * Primary navigation.
 *
 * Each role gets its own items and nothing else. A reviewer cannot reach
 * `/applications` — the server returns 403 — so showing them the link would be
 * offering a dead end. Navigation is derived from the role rather than filtered
 * after the fact, so the two cannot drift.
 */

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  /** Longest-prefix match, so `/applications/abc` still highlights Applications. */
  matchPrefix: string;
}

const ADMIN_NAV: NavItem[] = [
  { href: "/admin-dashboard", label: "Dashboard", icon: LayoutDashboard, matchPrefix: "/admin-dashboard" },
  { href: "/admin/applications", label: "Applications", icon: FileText, matchPrefix: "/admin/applications" },
  { href: "/admin/agencies", label: "Agencies", icon: Building2, matchPrefix: "/admin/agencies" },
  { href: "/admin/users", label: "Users", icon: Users, matchPrefix: "/admin/users" },
  { href: "/admin/routing", label: "Routing", icon: Route, matchPrefix: "/admin/routing" },
];

const ORGANIZER_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, matchPrefix: "/dashboard" },
  {
    href: "/applications",
    label: "Applications",
    icon: FileText,
    matchPrefix: "/applications",
  },
];

const REVIEWER_NAV: NavItem[] = [
  { href: "/queue", label: "Review queue", icon: ClipboardList, matchPrefix: "/queue" },
];

function navForRole(role: string | undefined): NavItem[] {
  if (role === "City Admin") return ADMIN_NAV;
  if (role === "Agency Reviewer") return REVIEWER_NAV;
  if (role === "Organizer") return ORGANIZER_NAV;
  return [];
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useSession();
  const items = navForRole(user?.role);

  if (items.length === 0) return null;

  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-3">
      {items.map((item) => {
        const active = pathname.startsWith(item.matchPrefix);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex items-center gap-2.5 rounded-control px-2.5 py-2",
              "text-[13px] font-medium transition-colors duration-150",
              active
                ? "bg-brand-50 text-brand-800"
                : "text-ink-600 hover:bg-ink-50 hover:text-ink-900",
            )}
          >
            {/* A rail marker rather than a filled pill: quieter, and it keeps the
                label's position identical between states so nothing shifts. */}
            <span
              aria-hidden
              className={cn(
                "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r-full transition-opacity",
                active ? "bg-brand-600 opacity-100" : "opacity-0",
              )}
            />
            <Icon
              aria-hidden
              className={cn(
                "size-4 shrink-0 transition-colors",
                active ? "text-brand-600" : "text-ink-400 group-hover:text-ink-600",
              )}
            />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** The product mark and wordmark. Also the mobile sheet's header. */
export function SidebarBrand() {
  return (
    <Link
      href="/dashboard"
      className="flex items-center gap-2.5 rounded-control px-3 py-1 transition-opacity hover:opacity-80"
    >
      <Logo />
      <span className="text-[15px] font-semibold tracking-tight text-ink-900">PermitFlow</span>
    </Link>
  );
}

/** The signed-in identity block. Role, never a fabricated city or agency name. */
export function SidebarIdentity() {
  const { user, signOut } = useSession();
  if (!user) return null;

  const role = rolePresentation(user.role);
  const workspace = user.role === "Agency Reviewer" ? "Agency workspace" : "City workspace";

  return (
    <div className="border-t border-line p-3">
      <div className="flex items-center gap-2.5 rounded-control px-1.5 py-1.5">
        <Avatar>
          <AvatarFallback>{initialFromEmail(user.email)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink-900">{user.email}</p>
          <p className="truncate text-[11px] text-ink-500">{role.label}</p>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        block
        icon={<LogOut />}
        onClick={signOut}
        className="mt-1 justify-start text-ink-500 hover:text-ink-900"
      >
        Sign out
      </Button>
      <p className="mt-1 px-1.5 text-[10px] uppercase tracking-wide text-ink-300">{workspace}</p>
    </div>
  );
}

/**
 * Desktop sidebar.
 *
 * Fixed width, always visible from `lg`. Below that the shell renders
 * `MobileNav` instead — a sidebar that collapses to icons at `md` saves 200px but
 * makes every label ambiguous, which is a poor trade for a two-item nav.
 */
export function Sidebar() {
  const { user } = useSession();
  if (!user) return null;

  return (
    <aside className="hidden w-60 shrink-0 flex-col justify-between border-r border-line bg-surface lg:flex">
      <div className="flex flex-col gap-6 py-5">
        <div className="px-3">
          <SidebarBrand />
        </div>
        <SidebarNav />
      </div>

      <div className="flex flex-col gap-3">
        <div className="px-3">
          <p className="flex items-center gap-1.5 text-[11px] leading-relaxed text-ink-400">
            <ShieldCheck aria-hidden className="size-3.5 shrink-0" />
            Scoped to your city&rsquo;s data
          </p>
        </div>
        <SidebarIdentity />
      </div>
    </aside>
  );
}

/**
 * Mobile navigation sheet.
 *
 * A dialog, so it gets the focus trap, Escape handling and scroll locking for
 * free — all three are the usual complaints about hand-rolled mobile menus.
 */
export function MobileNav() {
  const [open, setOpen] = useState(false);

  // Closing is driven by the nav link's own click handler (`onNavigate`), not by
  // an effect watching the pathname. Leaving the sheet open across a route change
  // would hide the page the user just asked for, but re-syncing it from the URL
  // would mean an effect that sets state during render.

  return (
    <>
      <Button
        variant="default"
        size="icon"
        className="lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden className="size-4">
          <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="animate-overlay-in absolute inset-0 bg-ink-950/40 backdrop-blur-[2px]"
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="animate-pop-in absolute inset-y-0 left-0 flex w-64 flex-col justify-between border-r border-line bg-surface"
          >
            <div className="flex flex-col gap-6 py-5">
              <div className="flex items-center justify-between px-3">
                <SidebarBrand />
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation"
                >
                  <X aria-hidden />
                </Button>
              </div>
              <SidebarNav onNavigate={() => setOpen(false)} />
            </div>
            <SidebarIdentity />
          </div>
        </div>
      )}
    </>
  );
}

/** A footer link strip for the marketing surface. Not used inside the shell. */
export function MarketingLinks() {
  return (
    <div className="flex items-center gap-5 text-[13px] text-ink-500">
      <a href="#how-it-works" className="transition-colors hover:text-ink-900">
        How it works
      </a>
      <a href="#agencies" className="transition-colors hover:text-ink-900">
        Agencies
      </a>
      <a href="#access" className="flex items-center gap-1.5 transition-colors hover:text-ink-900">
        <LifeBuoy aria-hidden className="size-3.5" />
        Support
      </a>
      <span className="flex items-center gap-1.5 text-ink-400">
        <CheckCircle2 aria-hidden className="size-3.5" />
        SOC 2 in progress
      </span>
    </div>
  );
}