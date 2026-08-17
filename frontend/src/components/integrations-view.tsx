"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import {
  disconnectPlatform,
  generatePerformanceInsights,
  getConnectionMetrics,
  getPlatformAuthorizeUrl,
  listConnections,
  syncConnectionMetrics,
  type ConnectionStatus,
  type PlatformConnection,
  type PlatformMetricSnapshot,
  type SocialPlatform,
} from "@/lib/api";

const PLATFORM_LABELS: Record<SocialPlatform, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  twitter: "X (Twitter)",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  youtube: "YouTube",
};

const STATUS_BADGE_STYLES: Record<ConnectionStatus, string> = {
  connected: "bg-primary/15 text-primary",
  pending: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  disconnected: "",
  error: "bg-destructive/10 text-destructive",
  expired: "bg-destructive/10 text-destructive",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function IntegrationsView({
  companyId,
  connectError,
}: {
  companyId: string;
  connectError?: string;
}) {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listConnections(companyId)
      .then(({ items }) => setConnections(items))
      .catch((err) => setError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function handleDisconnect(connectionId: string) {
    setDisconnectingId(connectionId);
    setError(null);
    try {
      await disconnectPlatform(connectionId);
      refresh();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setDisconnectingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {connectError && (
        <Card className="border-destructive/40">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Connecting didn&apos;t complete: {connectError}. You can try again below.
            </p>
          </CardContent>
        </Card>
      )}

      <InsightsCard companyId={companyId} />

      {loading && <p className="text-sm text-muted-foreground">Loading connections…</p>}

      {!loading && (
        <div className="flex flex-col gap-3">
          {connections.map((connection) => (
            <PlatformCard
              key={connection.platform}
              companyId={companyId}
              connection={connection}
              disconnecting={disconnectingId === connection.id}
              expanded={expandedId === connection.id}
              onToggleExpand={() =>
                setExpandedId((prev) => (prev === connection.id ? null : connection.id))
              }
              onDisconnect={() => connection.id && handleDisconnect(connection.id)}
            />
          ))}
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

function InsightsCard({ companyId }: { companyId: string }) {
  const [insights, setInsights] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const res = await generatePerformanceInsights(companyId);
      setInsights(res.insights);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Performance insights</p>
          <Button size="sm" variant="outline" disabled={generating} onClick={handleGenerate}>
            {generating ? "Analyzing…" : insights ? "Regenerate" : "Generate insights"}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {insights && <p className="whitespace-pre-wrap text-sm text-muted-foreground">{insights}</p>}
        {!insights && !error && (
          <p className="text-sm text-muted-foreground">
            One Claude pass over this company&apos;s real stored metrics and published content — it
            says plainly when there isn&apos;t enough data yet rather than guessing.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PlatformCard({
  companyId,
  connection,
  disconnecting,
  expanded,
  onToggleExpand,
  onDisconnect,
}: {
  companyId: string;
  connection: PlatformConnection;
  disconnecting: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onDisconnect: () => void;
}) {
  const isConnected = connection.status === "connected";
  const [connecting, setConnecting] = useState(false);

  async function handleConnect() {
    setConnecting(true);
    // Not a fetch call — this is a real browser navigation so the
    // platform's own consent screen can render. The session token has to
    // ride along as a query param since plain navigation can't carry a
    // custom Authorization header.
    window.location.href = await getPlatformAuthorizeUrl(connection.platform, companyId);
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{PLATFORM_LABELS[connection.platform]}</span>
            <Badge className={STATUS_BADGE_STYLES[connection.status]} variant="default">
              {isConnected && connection.external_account_name
                ? `Connected as ${connection.external_account_name}`
                : connection.status}
            </Badge>
          </div>

          <div className="flex gap-2">
            {isConnected && connection.id && (
              <Button variant="ghost" size="sm" onClick={onToggleExpand}>
                {expanded ? "Hide analytics" : "View analytics"}
              </Button>
            )}
            {isConnected && connection.id ? (
              <Button variant="outline" size="sm" disabled={disconnecting} onClick={onDisconnect}>
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </Button>
            ) : (
              <Button size="sm" disabled={connecting} onClick={handleConnect}>
                {connecting ? "Redirecting…" : "Connect"}
              </Button>
            )}
          </div>
        </div>

        {isConnected && connection.connected_at && (
          <p className="text-xs text-muted-foreground">
            Connected {formatDateTime(connection.connected_at)}
            {connection.scopes ? ` · scopes: ${connection.scopes}` : ""}
          </p>
        )}

        {connection.status === "error" && connection.status_error && (
          <p className="text-xs text-destructive">{connection.status_error}</p>
        )}

        {expanded && connection.id && <ConnectionMetrics connectionId={connection.id} />}
      </CardContent>
    </Card>
  );
}

function FollowerSparkline({ snapshots }: { snapshots: PlatformMetricSnapshot[] }) {
  // snapshots arrive newest-first; a sparkline reads left-to-right oldest-first.
  const points = snapshots
    .filter((s): s is PlatformMetricSnapshot & { follower_count: number } => s.follower_count !== null)
    .slice()
    .reverse();
  if (points.length < 2) return null;

  const width = 240;
  const height = 40;
  const values = points.map((p) => p.follower_count);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coords = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-10 w-full text-primary" preserveAspectRatio="none">
      <polyline points={coords} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function ConnectionMetrics({ connectionId }: { connectionId: string }) {
  const [snapshots, setSnapshots] = useState<PlatformMetricSnapshot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  function load() {
    getConnectionMetrics(connectionId)
      .then(({ items }) => setSnapshots(items))
      .catch((err) => setError(describeError(err)));
  }

  useEffect(() => {
    // No reset-on-change needed here: this component only ever mounts with
    // a single connectionId for its whole lifetime — the parent
    // conditionally renders it (expanded && ...), so a different
    // connection means a fresh mount, not a prop change on this one.
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId]);

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncConnectionMetrics(connectionId);
      load();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="rounded-md border border-border bg-muted/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-medium text-muted-foreground">Metrics</p>
        <Button size="xs" variant="ghost" onClick={handleSync} disabled={syncing}>
          {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {!error && snapshots === null && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!error && snapshots !== null && snapshots.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No metrics yet — nothing has been collected for this connection so far. This fills in
          automatically once it does; nothing shown here is estimated or simulated.
        </p>
      )}
      {!error && snapshots !== null && snapshots.length > 0 && (
        <div className="flex flex-col gap-2">
          <FollowerSparkline snapshots={snapshots} />
          <div className="flex flex-col gap-1.5">
            {snapshots.map((snapshot) => (
              <div key={snapshot.id} className="flex justify-between text-sm">
                <span className="text-muted-foreground">{formatDateTime(snapshot.captured_at)}</span>
                <span>
                  {snapshot.follower_count !== null ? `${snapshot.follower_count} followers` : "—"}
                  {snapshot.engagement_rate !== null
                    ? ` · ${(snapshot.engagement_rate * 100).toFixed(1)}% engagement`
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
