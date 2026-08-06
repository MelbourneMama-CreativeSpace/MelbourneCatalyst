"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

import { triggerCollection } from "@/lib/api";

// The one real, wired action in this page's Quick Actions — everything
// else here is a link, this is the one thing that actually does
// something in place: kicks off a real collection run
// (POST /trend-analyzer/collect) and refreshes the page's server data
// once it's done.
export function TriggerCollectionButton() {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(false);

  async function handleClick() {
    setRunning(true);
    setError(false);
    try {
      await triggerCollection();
      router.refresh();
    } catch {
      setError(true);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={handleClick}
        disabled={running}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-50"
      >
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
        {running ? "Running collection…" : "Run a new collection"}
      </button>
      {error && (
        <p className="mt-1.5 text-center text-xs text-destructive">
          Couldn&apos;t start a collection run — try again.
        </p>
      )}
    </div>
  );
}
