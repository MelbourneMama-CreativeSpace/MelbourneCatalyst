"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function IntegrationsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-bold">Couldn&apos;t load social connections</h1>
      <p className="max-w-md text-muted-foreground">
        The Social Media Analyzer API didn&apos;t respond as expected. This usually means the
        backend isn&apos;t reachable yet, or its database isn&apos;t configured.
      </p>
      <p className="max-w-md text-xs text-muted-foreground/70">{error.message}</p>
      <div className="flex gap-3">
        <Button onClick={() => reset()}>Try again</Button>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href="/companies">Back to companies</Link>}
        />
      </div>
    </div>
  );
}
