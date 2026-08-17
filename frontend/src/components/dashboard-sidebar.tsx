"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MessageSquare,
  Menu,
  Plug,
  SquarePen,
  TrendingUp,
  Users,
  X,
} from "lucide-react";

import { AuthHeader } from "@/components/auth-header";
import { ConversationList } from "@/components/conversation-list";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  showCount?: boolean;
}

// Approvals and Publish Monitor are restricted for now — routes/pages
// still exist, just not linked from here. Re-add the two entries below
// (and restore the pendingCount polling this file used to do for
// Approvals' badge) to bring them back.
const navItems: NavItem[] = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Content Studio", icon: Users },
  { href: "/analysis", label: "Analysis", icon: BarChart3 },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/trends", label: "Trends", icon: TrendingUp },
];

function SidebarContent({
  initialEmail,
  initialName,
  collapsed,
  onToggle,
}: {
  initialEmail: string | null;
  initialName: string | null;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const pathname = usePathname();
  // No nav item currently sets showCount (Approvals, the only one that
  // did, is restricted for now — see the comment above navItems), so
  // this stays null; the badge JSX below is dead until that changes,
  // left in place rather than deleted since it's generic, not
  // Approvals-specific.
  const pendingCount: number | null = null;

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground overflow-hidden">

      {/* Logo + toggle in one row */}
      <div className={`flex items-center py-4 ${collapsed ? "flex-col gap-2 px-2 pt-3" : "px-4 gap-2"}`}>
        {collapsed ? (
          <>
            {/* Toggle on top when collapsed */}
            <button
              type="button"
              aria-label="Expand sidebar"
              onClick={onToggle}
              className="flex h-6 w-6 items-center justify-center rounded-md text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
            <Image
              src="/loomverse-mark.png"
              alt="LoomVerse AI"
              width={28}
              height={28}
              priority
            />
          </>
        ) : (
          <>
            {/* Mark-only image + real text (not baked into an image) —
                same navy/teal brand colors and weight as the wordmark. */}
            <div className="flex items-center gap-2">
              <Image
                src="/loomverse-mark.png"
                alt="LoomVerse AI"
                width={26}
                height={26}
                priority
              />
              <p className="flex items-baseline leading-none">
                <span className="text-base font-bold uppercase tracking-wide text-foreground">
                  Loomverse
                </span>
                <span className="ml-0.5 text-xs font-medium normal-case tracking-normal text-primary">
                  .ai
                </span>
              </p>
            </div>
            {/* Push toggle to the far right */}
            <div className="flex-1" />
            <button
              type="button"
              aria-label="Collapse sidebar"
              onClick={onToggle}
              className="flex h-6 w-6 items-center justify-center rounded-md text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>

      {/* Nav items */}
      <nav className={`flex flex-col gap-1 ${collapsed ? "px-2" : "px-3"}`}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`group relative flex items-center rounded-lg transition-colors
                ${collapsed ? "justify-center px-2 py-2.5" : "gap-2.5 px-3 py-2"}
                ${
                  active
                    ? "bg-sidebar-accent text-sidebar-foreground font-medium"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                }`}
            >
              <Icon className="h-4 w-4 shrink-0" />

              {/* Label — hidden when collapsed */}
              {!collapsed && (
                <>
                  <span className="flex-1 text-sm">{item.label}</span>
                  {item.showCount && !!pendingCount && (
                    <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                      {pendingCount}
                    </span>
                  )}
                </>
              )}

              {/* Badge dot when collapsed & there's a count */}
              {collapsed && item.showCount && !!pendingCount && (
                <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-primary" />
              )}

              {/* Tooltip on collapsed icons */}
              {collapsed && (
                <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background opacity-0 shadow-md transition-opacity group-hover:opacity-100">
                  {item.label}
                  {item.showCount && !!pendingCount ? ` (${pendingCount})` : ""}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* New Chat — always visible/clickable, unlike the "Chat" nav item
          above, which shows as active (and easy to assume does nothing)
          while already inside a conversation. Goes to the plain /chat
          index route, which is itself the empty-composer "start a new
          conversation" screen. */}
      <div className={`mt-3 ${collapsed ? "px-2" : "px-3"}`}>
        <Link
          href="/chat"
          title={collapsed ? "New chat" : undefined}
          className={`group relative flex items-center rounded-lg border border-sidebar-border text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors
            ${collapsed ? "justify-center px-2 py-2.5" : "gap-2.5 px-3 py-2"}`}
        >
          <SquarePen className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="text-sm font-medium">New chat</span>}
          {collapsed && (
            <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background opacity-0 shadow-md transition-opacity group-hover:opacity-100">
              New chat
            </span>
          )}
        </Link>
      </div>

      {/* Conversations — hidden when collapsed */}
      {!collapsed && (
        <div className="mt-4 flex-1 min-h-0 px-3">
          <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-sidebar-foreground/50">
            Conversations
          </p>
          <div className="h-full overflow-y-auto pb-4">
            <ConversationList />
          </div>
        </div>
      )}

      {/* Spacer when collapsed so footer stays at bottom */}
      {collapsed && <div className="flex-1" />}

      {/* Footer / auth */}
      <div className="border-t border-sidebar-border">
        <AuthHeader initialEmail={initialEmail} initialName={initialName} collapsed={collapsed} />
      </div>
    </div>
  );
}

export function DashboardSidebar({
  initialEmail,
  initialName,
}: {
  initialEmail: string | null;
  initialName: string | null;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* ── Desktop sidebar ── */}
      <aside
        className={`hidden md:flex md:shrink-0 md:flex-col md:border-r md:border-sidebar-border transition-all duration-300 ease-in-out
          ${collapsed ? "md:w-14" : "md:w-64"}`}
      >
        <SidebarContent
          initialEmail={initialEmail}
          initialName={initialName}
          collapsed={collapsed}
          onToggle={() => setCollapsed((v) => !v)}
        />
      </aside>

      {/* ── Mobile: top bar + slide-in panel ── */}
      <div className="flex items-center justify-between border-b border-sidebar-border bg-sidebar px-4 py-3 md:hidden">
        <Image src="/loomverse-mark.png" alt="LoomVerse AI" width={28} height={28} />
        <button
          type="button"
          aria-label="Open menu"
          onClick={() => setMobileOpen(true)}
          className="rounded-md p-2 text-sidebar-foreground hover:bg-sidebar-accent"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
          />
          <div className="animate-slide-in-left absolute inset-y-0 left-0 w-72 shadow-xl">
            <div className="flex items-center justify-end px-3 py-3">
              <button
                type="button"
                aria-label="Close menu"
                onClick={() => setMobileOpen(false)}
                className="rounded-md p-2 text-sidebar-foreground hover:bg-sidebar-accent"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="h-[calc(100%-3rem)]">
              <SidebarContent
                initialEmail={initialEmail}
                initialName={initialName}
                collapsed={false}
                onToggle={() => {}}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
