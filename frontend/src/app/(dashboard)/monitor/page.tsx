"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RotateCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { listPublishAttempts, retryPublishAttempt, type PublishAttempt } from "@/lib/api";

const STATUS_FILTERS = ["all", "failed", "success"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

export default function MonitorPage() {
  const [attempts, setAttempts] = useState<PublishAttempt[] | null>(null);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [retryingId, setRetryingId] = useState<string | null>(null);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  function load() {
    setError(false);
    listPublishAttempts(statusFilter === "all" ? {} : { status: statusFilter })
      .then((res) => setAttempts(res.items))
      .catch(() => setError(true));
  }

  async function handleRetry(attempt: PublishAttempt) {
    setRetryingId(attempt.id);
    try {
      await retryPublishAttempt(attempt.id);
      load();
    } catch {
      // Leave the row as-is — the user can try again.
    } finally {
      setRetryingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold">Publish Monitor</h1>
      <p className="mt-1 text-muted-foreground">
        Every publish attempt this app has made, across every client — not live platform
        engagement (see Integrations for that once connected).
      </p>

      <div className="mt-6 flex gap-2">
        {STATUS_FILTERS.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={statusFilter === s ? "default" : "outline"}
            onClick={() => setStatusFilter(s)}
            className="capitalize"
          >
            {s}
          </Button>
        ))}
      </div>

      <div className="mt-6 flex flex-col gap-3">
        {error && <p className="text-sm text-destructive">Couldn&apos;t load publish attempts.</p>}
        {attempts !== null && attempts.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">No publish attempts yet.</p>
        )}
        {attempts?.map((attempt) => (
          <Card key={attempt.id}>
            <CardContent className="flex items-center justify-between gap-4 py-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {attempt.status === "success" ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
                  )}
                  <Badge variant="outline" className="capitalize">
                    {attempt.platform}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {attempt.company_name ?? "Unknown company"}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm font-medium">{attempt.content_item_title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {new Date(attempt.attempted_at).toLocaleString()}
                  {attempt.status_error ? ` — ${attempt.status_error}` : ""}
                </p>
              </div>
              {attempt.status === "failed" && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={retryingId === attempt.id}
                  onClick={() => handleRetry(attempt)}
                  className="shrink-0 gap-1.5"
                >
                  <RotateCw className="h-3.5 w-3.5" />
                  {retryingId === attempt.id ? "Retrying…" : "Retry"}
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
