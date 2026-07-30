"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function TrendsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-bold">Couldn&apos;t load trends</h1>
      <p className="max-w-md text-muted-foreground">
        The Trend Analyzer API didn&apos;t respond as expected. This usually means the
        backend isn&apos;t reachable yet, or its database isn&apos;t configured — check{" "}
        <code className="rounded bg-muted px-1.5 py-0.5">DATABASE_URL</code> in{" "}
        <code className="rounded bg-muted px-1.5 py-0.5">backend/.env</code>.
      </p>
      <p className="max-w-md text-xs text-muted-foreground/70">{error.message}</p>
      <div className="flex gap-3">
        <Button onClick={() => reset()}>Try again</Button>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href="/">Back to home</Link>}
        />
      </div>
    </div>
  );
}
