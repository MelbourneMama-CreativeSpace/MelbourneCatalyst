"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import {
  getCampaign,
  updateCampaignLifecycle,
  type Campaign,
  type LifecycleStage,
} from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<Campaign["status"]> = new Set(["complete", "failed"]);

const LIFECYCLE_STAGES: LifecycleStage[] = [
  "draft",
  "scheduled",
  "active",
  "completed",
  "archived",
];

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function CampaignView({ initialCampaign }: { initialCampaign: Campaign }) {
  const [campaign, setCampaign] = useState(initialCampaign);
  const [updatingStage, setUpdatingStage] = useState(false);
  const [stageError, setStageError] = useState<string | null>(null);

  // Campaign generation is a synchronous POST, so this row should already be
  // terminal by the time this page renders — poll defensively in case it's
  // ever viewed mid-generation (e.g. a second tab), same as StrategyView.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(campaign.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getCampaign(campaign.id);
        setCampaign(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [campaign.id, campaign.status]);

  async function handleSetStage(stage: LifecycleStage) {
    if (stage === campaign.lifecycle_stage) return;
    setUpdatingStage(true);
    setStageError(null);
    try {
      const updated = await updateCampaignLifecycle(campaign.id, stage);
      setCampaign(updated);
    } catch (err) {
      setStageError(describeError(err));
    } finally {
      setUpdatingStage(false);
    }
  }

  const statusVariant = campaign.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">{campaign.name ?? "Campaign"}</h1>
        <Badge variant={statusVariant}>{campaign.status}</Badge>
      </div>

      {campaign.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Campaign generation failed{campaign.status_error ? `: ${campaign.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(campaign.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Generating campaign…</p>
          </CardContent>
        </Card>
      )}

      {campaign.status === "complete" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Lifecycle stage</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              {LIFECYCLE_STAGES.map((stage) => (
                <Button
                  key={stage}
                  size="sm"
                  variant={stage === campaign.lifecycle_stage ? "default" : "outline"}
                  disabled={updatingStage}
                  onClick={() => handleSetStage(stage)}
                >
                  {stage}
                </Button>
              ))}
            </div>
            {stageError && <p className="text-sm text-destructive">{stageError}</p>}
          </CardContent>
        </Card>
      )}

      {(campaign.start_date || campaign.end_date) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              {campaign.start_date ? formatDate(campaign.start_date) : "TBD"}
              {" — "}
              {campaign.end_date ? formatDate(campaign.end_date) : "TBD"}
            </p>
          </CardContent>
        </Card>
      )}

      <CampaignField label="Objective" value={campaign.objective} />
      <CampaignField label="Budget allocation" value={campaign.budget_allocation} />
      <CampaignField label="Success metrics" value={campaign.success_metrics} />
    </div>
  );
}

function CampaignField({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed whitespace-pre-line">{value}</p>
      </CardContent>
    </Card>
  );
}
