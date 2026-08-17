"use client";

import { useEffect, useRef, type ReactNode } from "react";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/toast";
import { describeError } from "@/lib/api-error";

/**
 * Shared body for every route-level `error.tsx` boundary. `describeError`
 * turns whatever actually broke (a network failure, an HTTP status, a
 * rendering bug) into one plain sentence with no technical detail in it —
 * see `lib/api-error.ts` — and that sentence is the *only* thing shown to
 * the person, both here and as a bottom-right toast for consistency with
 * how every other error/success message in the app is surfaced. The real
 * `error` (with its digest, stack, and any backend detail) still goes to
 * the console for whoever needs to actually debug it — never onto the
 * screen itself.
 */
export function ErrorState({
  title,
  hint,
  error,
  reset,
  backHref,
  backLabel,
}: {
  /** e.g. "Couldn't load this strategy" */
  title: string;
  /** One human, non-technical sentence of page-specific context. */
  hint: ReactNode;
  error: Error & { digest?: string };
  reset: () => void;
  backHref: string;
  backLabel: string;
}) {
  const toast = useToast();
  const message = describeError(error);
  // React 18 Strict Mode (on by default in Next dev) mounts, cleans up,
  // and re-mounts every component once — this effect would otherwise fire
  // twice per real error and stack two identical toasts. A ref survives
  // that cleanup/remount cycle within the same logical mount, so it's a
  // correct guard rather than a dev-only workaround.
  const hasNotified = useRef(false);

  useEffect(() => {
    if (hasNotified.current) return;
    hasNotified.current = true;
    // Logged, never rendered — this is the one place the real error
    // detail goes.
    console.error(error);
    toast.error(message);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per mount, not on every toast/message identity change
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="max-w-md text-muted-foreground">{hint}</p>
      <div className="flex gap-3">
        <Button onClick={() => reset()}>Try again</Button>
        <Button variant="outline" nativeButton={false} render={<Link href={backHref}>{backLabel}</Link>} />
      </div>
    </div>
  );
}
