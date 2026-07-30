"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { createClient } from "@/lib/supabase/client";

type Mode = "sign-in" | "sign-up";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = searchParams.get("redirectTo") || "/dashboard";

  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signUpConfirmSent, setSignUpConfirmSent] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSignUpConfirmSent(false);

    const supabase = createClient();

    if (mode === "sign-in") {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) {
        setError(signInError.message);
        setSubmitting(false);
        return;
      }
      router.push(redirectTo);
      router.refresh();
      return;
    }

    const { data, error: signUpError } = await supabase.auth.signUp({ email, password });
    if (signUpError) {
      setError(signUpError.message);
      setSubmitting(false);
      return;
    }
    if (data.session) {
      // Email confirmation is off for this project — signUp already
      // returned a live session, so there's nothing left to wait for.
      router.push(redirectTo);
      router.refresh();
      return;
    }
    setSignUpConfirmSent(true);
    setSubmitting(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col gap-5 pt-6">
          <div>
            <h1 className="text-xl font-bold">LoomVerse AI</h1>
            <p className="text-sm text-muted-foreground">
              {mode === "sign-in" ? "Sign in to continue." : "Create an account for the team."}
            </p>
          </div>

          {signUpConfirmSent ? (
            <p className="text-sm text-muted-foreground">
              Check {email} for a confirmation link, then sign in.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Email
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  className="rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Password
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
                  className="rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                />
              </label>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" disabled={submitting} className="mt-1">
                {submitting
                  ? mode === "sign-in"
                    ? "Signing in…"
                    : "Creating account…"
                  : mode === "sign-in"
                    ? "Sign in"
                    : "Create account"}
              </Button>
            </form>
          )}

          <p className="text-xs text-muted-foreground">
            {mode === "sign-in" ? "Need an account?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "sign-in" ? "sign-up" : "sign-in");
                setError(null);
                setSignUpConfirmSent(false);
              }}
              className="text-foreground underline hover:no-underline"
            >
              {mode === "sign-in" ? "Create one" : "Sign in instead"}
            </button>
          </p>

          <Link href="/" className="text-xs text-muted-foreground hover:text-foreground">
            &larr; Back home
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
