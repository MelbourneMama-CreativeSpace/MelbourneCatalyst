"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Plug } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PlatformIcon, PLATFORM_LABELS } from "@/components/social-icons";
import {
  disconnectPlatform,
  getPlatformAuthorizeUrl,
  listCompanies,
  listConnections,
  type Company,
  type PlatformConnection,
} from "@/lib/api";

// This app manages one business's own social presence, not a roster of
// clients, so — unlike a "pick a client" list — this resolves straight to
// the one company on the account and shows its platform connections
// directly: a logo + a single Connect/Disconnect button per platform,
// nothing else in the way. (If an account somehow has more than one
// company, this uses the first — each company's fuller connection detail,
// with analytics, still lives at /integrations/[companyId].)
export default function IntegrationsPage() {
  const [company, setCompany] = useState<Company | null>(null);
  const [loadingCompany, setLoadingCompany] = useState(true);
  const [connections, setConnections] = useState<PlatformConnection[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    listCompanies()
      .then(async (res) => {
        const primary = res.items[0] ?? null;
        setCompany(primary);
        setLoadingCompany(false);
        if (primary) {
          const { items } = await listConnections(primary.id);
          setConnections(items);
        }
      })
      .catch(() => {
        setError(true);
        setLoadingCompany(false);
      });
  }, []);

  function handleConnectionChange(updated: PlatformConnection) {
    setConnections((prev) => prev?.map((c) => (c.platform === updated.platform ? updated : c)) ?? prev);
  }

  const connectedList = connections?.filter((c) => c.status === "connected") ?? [];
  const notConnectedList = connections?.filter((c) => c.status !== "connected") ?? [];

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center gap-2">
        <Plug className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold">Integrations</h1>
      </div>
      <p className="mt-1 text-muted-foreground">
        Connect your social accounts so LoomVerse AI can publish to them and track performance.
      </p>

      {error && <p className="mt-6 text-sm text-destructive">Couldn&apos;t load this — try again.</p>}

      {!error && loadingCompany && <p className="mt-6 text-sm text-muted-foreground">Loading…</p>}

      {!error && !loadingCompany && !company && (
        <p className="mt-6 text-sm text-muted-foreground">
          Set up your company profile first —{" "}
          <Link href="/onboarding" className="underline hover:text-foreground">
            add your website
          </Link>{" "}
          so LoomVerse AI understands what you do, then come back here to connect your accounts.
        </p>
      )}

      {company && (
        <div className="mt-6 flex flex-col gap-8">
          <Link
            href={`/integrations/${company.id}`}
            className="flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            View analytics for connected accounts
            <ArrowRight className="h-3 w-3" />
          </Link>

          <section>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Connect
            </h2>
            {connections === null ? (
              <p className="text-sm text-muted-foreground">Loading connections…</p>
            ) : notConnectedList.length === 0 ? (
              <p className="text-sm text-muted-foreground">Everything&apos;s connected.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {notConnectedList.map((connection) => (
                  <PlatformRow
                    key={connection.platform}
                    companyId={company.id}
                    connection={connection}
                    onChange={handleConnectionChange}
                  />
                ))}
              </div>
            )}
          </section>

          {connectedList.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Manage connections
              </h2>
              <div className="flex flex-col gap-2">
                {connectedList.map((connection) => (
                  <PlatformRow
                    key={connection.platform}
                    companyId={company.id}
                    connection={connection}
                    onChange={handleConnectionChange}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function PlatformRow({
  companyId,
  connection,
  onChange,
}: {
  companyId: string;
  connection: PlatformConnection;
  onChange: (updated: PlatformConnection) => void;
}) {
  const [busy, setBusy] = useState(false);
  const isConnected = connection.status === "connected";

  async function handleConnect() {
    setBusy(true);
    // Real browser navigation, not a fetch — the platform's own consent
    // screen has to render. See getPlatformAuthorizeUrl's own comment for
    // why this can't just be a plain <a href>.
    window.location.href = await getPlatformAuthorizeUrl(connection.platform, companyId);
  }

  async function handleDisconnect() {
    if (!connection.id) return;
    setBusy(true);
    try {
      const updated = await disconnectPlatform(connection.id);
      onChange(updated);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <PlatformIcon platform={connection.platform} className="h-6 w-6 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{PLATFORM_LABELS[connection.platform]}</p>
          {isConnected && connection.external_account_name && (
            <p className="truncate text-xs text-muted-foreground">
              Connected as {connection.external_account_name}
            </p>
          )}
          {connection.status === "error" && connection.status_error && (
            <p className="truncate text-xs text-destructive">{connection.status_error}</p>
          )}
        </div>
      </div>

      {isConnected ? (
        <Button size="sm" variant="outline" disabled={busy} onClick={handleDisconnect}>
          {busy ? "Disconnecting…" : "Disconnect"}
        </Button>
      ) : (
        <Button size="sm" disabled={busy} onClick={handleConnect}>
          {busy ? "Redirecting…" : "Connect"}
        </Button>
      )}
    </div>
  );
}
