"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function AuthHeader({
  initialEmail,
  initialName,
  collapsed = false,
}: {
  initialEmail: string | null;
  initialName: string | null;
  collapsed?: boolean;
}) {
  const router = useRouter();
  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState(initialName);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
      const fullName = session?.user.user_metadata?.full_name;
      setName(typeof fullName === "string" && fullName ? fullName : null);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  if (!email) return null;

  const displayName = name ?? email;
  const initial = displayName.charAt(0).toUpperCase();

  /* ── Collapsed: just an avatar + sign-out icon with tooltips ── */
  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1 py-3">
        {/* Avatar */}
        <div
          className="group relative flex h-7 w-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary"
          title={displayName}
        >
          {initial}
          <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background opacity-0 shadow-md transition-opacity group-hover:opacity-100">
            {displayName}
          </span>
        </div>

        {/* Sign out */}
        <button
          type="button"
          onClick={handleSignOut}
          disabled={signingOut}
          title="Sign out"
          className="group relative flex h-7 w-7 items-center justify-center rounded-lg text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground disabled:opacity-40 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background opacity-0 shadow-md transition-opacity group-hover:opacity-100">
            Sign out
          </span>
        </button>
      </div>
    );
  }

  /* ── Expanded: full name + sign out button ── */
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 text-xs text-sidebar-foreground/70">
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
          {initial}
        </div>
        <span className="truncate">{displayName}</span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        disabled={signingOut}
        onClick={handleSignOut}
        className="shrink-0 text-sidebar-foreground/70 hover:text-sidebar-foreground"
      >
        {signingOut ? "…" : "Sign out"}
      </Button>
    </div>
  );
}
