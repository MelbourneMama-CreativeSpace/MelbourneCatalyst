"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  FileEdit,
  LayoutDashboard,
  MessageSquare,
  Menu,
  Plus,
  Radio,
  TrendingUp,
  Users,
  X,
} from "lucide-react";

import { AuthHeader } from "@/components/auth-header";
import { ConversationList } from "@/components/conversation-list";
import { listPendingApprovals } from "@/lib/api";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Content Studio", icon: Users },
  { href: "/onboarding", label: "Add a client", icon: Plus },
  { href: "/drafts", label: "Drafts", icon: FileEdit },
  { href: "/trends", label: "Trends", icon: TrendingUp },
  { href: "/approvals", label: "Approvals", icon: CheckCircle2, showCount: true },
  { href: "/monitor", label: "Publish Monitor", icon: Radio },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];

function SidebarContent({ initialEmail }: { initialEmail: string | null }) {
  const pathname = usePathname();
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  useEffect(() => {
    listPendingApprovals()
      .then((res) => setPendingCount(res.total))
      .catch(() => setPendingCount(null));
    // Re-check whenever the route changes, so approving/rejecting an item
    // updates the badge without a full page reload.
  }, [pathname]);

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 py-4">
        <Image src="/loomverse-logo.png" alt="LoomVerse AI" width={130} height={32} priority />
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-sidebar-accent text-sidebar-foreground font-medium"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{item.label}</span>
              {item.showCount && !!pendingCount && (
                <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                  {pendingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 flex-1 min-h-0 px-3">
        <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-sidebar-foreground/50">
          Conversations
        </p>
        <div className="h-full overflow-y-auto pb-4">
          <ConversationList />
        </div>
      </div>

      <div className="border-t border-sidebar-border">
        <AuthHeader initialEmail={initialEmail} />
      </div>
    </div>
  );
}

export function DashboardSidebar({ initialEmail }: { initialEmail: string | null }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop: persistent sidebar */}
      <aside className="hidden md:flex md:w-64 md:shrink-0 md:flex-col md:border-r md:border-sidebar-border">
        <SidebarContent initialEmail={initialEmail} />
      </aside>

      {/* Mobile: toggle button + slide-in panel */}
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
              <SidebarContent initialEmail={initialEmail} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
