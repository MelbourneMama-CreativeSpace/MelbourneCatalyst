"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  disconnectPlatform,
  getConnectionMetrics,
  getPlatformAuthorizeUrl,
  listConnections,
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
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load connections."))
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
      setError(err instanceof Error ? err.message : "Failed to disconnect.");
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
              <Button
                size="sm"
                render={<a href={getPlatformAuthorizeUrl(connection.platform, companyId)} />}
                nativeButton={false}
              >
                Connect
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

function ConnectionMetrics({ connectionId }: { connectionId: string }) {
  const [snapshots, setSnapshots] = useState<PlatformMetricSnapshot[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // No reset-on-change needed here: this component only ever mounts with
    // a single connectionId for its whole lifetime — the parent
    // conditionally renders it (expanded && ...), so a different
    // connection means a fresh mount, not a prop change on this one.
    getConnectionMetrics(connectionId)
      .then(({ items }) => setSnapshots(items))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load metrics."));
  }, [connectionId]);

  return (
    <div className="rounded-md border border-border bg-muted/40 p-3">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!error && snapshots === null && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!error && snapshots !== null && snapshots.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No metrics yet — nothing has been collected for this connection so far. This fills in
          automatically once it does; nothing shown here is estimated or simulated.
        </p>
      )}
      {!error && snapshots !== null && snapshots.length > 0 && (
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
      )}
    </div>
  );
}
