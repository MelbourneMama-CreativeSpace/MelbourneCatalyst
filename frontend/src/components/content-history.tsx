"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  listCampaigns,
  listCollaborations,
  listContentPlans,
  listStrategies,
  type Campaign,
  type CollaborationSummary,
  type ContentPlanSummary,
  type GenerationStatus,
  type Strategy,
} from "@/lib/api";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function statusVariant(status: GenerationStatus): "default" | "outline" {
  return status === "complete" ? "default" : "outline";
}

interface HistoryEntry {
  id: string;
  created_at: string;
  status: GenerationStatus;
}

function HistoryList({
  title,
  entries,
  hrefPrefix,
}: {
  title: string;
  entries: HistoryEntry[];
  hrefPrefix: string;
}) {
  if (entries.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2">
          {entries.map((entry) => (
            <li key={entry.id}>
              <Link
                href={`${hrefPrefix}/${entry.id}`}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
              >
                <span className="truncate text-muted-foreground">
                  {formatDateTime(entry.created_at)}
                </span>
                <Badge variant={statusVariant(entry.status)}>{entry.status}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function ContentHistory({ companyId }: { companyId: string }) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [contentPlans, setContentPlans] = useState<ContentPlanSummary[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [collaborations, setCollaborations] = useState<CollaborationSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    listStrategies(companyId)
      .then(({ items }) => {
        if (!cancelled) setStrategies(items);
      })
      .catch(() => {});
    listContentPlans(companyId)
      .then(({ items }) => {
        if (!cancelled) setContentPlans(items);
      })
      .catch(() => {});
    listCampaigns(companyId)
      .then(({ items }) => {
        if (!cancelled) setCampaigns(items);
      })
      .catch(() => {});
    listCollaborations(companyId)
      .then(({ items }) => {
        if (!cancelled) setCollaborations(items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  if (
    strategies.length === 0 &&
    contentPlans.length === 0 &&
    campaigns.length === 0 &&
    collaborations.length === 0
  ) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <HistoryList title="Past strategies" entries={strategies} hrefPrefix="/strategy" />
      <HistoryList title="Past content plans" entries={contentPlans} hrefPrefix="/content-plan" />
      <HistoryList title="Past campaigns" entries={campaigns} hrefPrefix="/campaign" />
      <HistoryList title="Past collaborations" entries={collaborations} hrefPrefix="/collaboration" />
    </div>
  );
}
