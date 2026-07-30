"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function AuthHeader({ initialEmail }: { initialEmail: string | null }) {
  const router = useRouter();
  const [email, setEmail] = useState(initialEmail);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
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

  return (
    <div className="flex items-center justify-end gap-3 border-b border-border/50 px-6 py-2 text-xs text-muted-foreground">
      <span>{email}</span>
      <Button variant="ghost" size="sm" disabled={signingOut} onClick={handleSignOut}>
        {signingOut ? "Signing out…" : "Sign out"}
      </Button>
    </div>
  );
}
