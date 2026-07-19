"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  disconnectPlatform,
  getPlatformAuthorizeUrl,
  listConnections,
  type PlatformConnection,
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

export function PlatformConnections({ companyId }: { companyId: string }) {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listConnections(companyId)
      .then(({ items }) => setConnections(items))
      .catch(() => {});
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

  if (connections.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Connected platforms</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {connections.map((connection) => {
          const isConnected = connection.status === "connected";
          return (
            <div
              key={connection.platform}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{PLATFORM_LABELS[connection.platform]}</span>
                {isConnected ? (
                  <Badge variant="default">
                    Connected{connection.external_account_name ? ` as ${connection.external_account_name}` : ""}
                  </Badge>
                ) : (
                  <Badge variant="outline">{connection.status}</Badge>
                )}
              </div>

              {isConnected && connection.id ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={disconnectingId === connection.id}
                  onClick={() => handleDisconnect(connection.id!)}
                >
                  {disconnectingId === connection.id ? "Disconnecting…" : "Disconnect"}
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
          );
        })}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
