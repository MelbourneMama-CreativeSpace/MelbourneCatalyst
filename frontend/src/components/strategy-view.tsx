"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createCollaboration, createContentPlan, getStrategy, type Strategy } from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<Strategy["status"]> = new Set(["complete", "failed"]);

const PLAN_WINDOWS: { label: string; days: number }[] = [
  { label: "Weekly", days: 7 },
  { label: "Standard", days: 14 },
  { label: "Monthly", days: 30 },
];

export function StrategyView({ initialStrategy }: { initialStrategy: Strategy }) {
  const router = useRouter();
  const [strategy, setStrategy] = useState(initialStrategy);
  const [planDays, setPlanDays] = useState(14);
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [generatingCollaboration, setGeneratingCollaboration] = useState(false);
  const [collaborationError, setCollaborationError] = useState<string | null>(null);

  // Strategy generation is a synchronous POST, so this row should already be
  // terminal by the time this page renders — poll defensively in case it's
  // ever viewed mid-generation (e.g. a second tab).
  useEffect(() => {
    if (TERMINAL_STATUSES.has(strategy.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getStrategy(strategy.id);
        setStrategy(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [strategy.id, strategy.status]);

  async function handleGenerateContentPlan() {
    setGeneratingPlan(true);
    setPlanError(null);
    try {
      const plan = await createContentPlan(strategy.company_id, strategy.id, planDays);
      router.push(`/content-plan/${plan.id}`);
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : "Failed to generate content plan.");
      setGeneratingPlan(false);
    }
  }

  async function handleGenerateCollaboration() {
    setGeneratingCollaboration(true);
    setCollaborationError(null);
    try {
      const collaboration = await createCollaboration(strategy.company_id, strategy.id);
      router.push(`/collaboration/${collaboration.id}`);
    } catch (err) {
      setCollaborationError(
        err instanceof Error ? err.message : "Failed to generate collaboration ideas.",
      );
      setGeneratingCollaboration(false);
    }
  }

  const statusVariant = strategy.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Marketing strategy</h1>
        <Badge variant={statusVariant}>{strategy.status}</Badge>
      </div>

      {strategy.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Strategy generation failed{strategy.status_error ? `: ${strategy.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(strategy.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Generating strategy…</p>
          </CardContent>
        </Card>
      )}

      <StrategyField label="Summary" value={strategy.summary} />
      <StrategyField label="Marketing strategy" value={strategy.marketing_strategy} />
      <StrategyField label="Campaign direction" value={strategy.campaign_direction} />
      <StrategyField label="Growth recommendations" value={strategy.growth_recommendations} />
      <StrategyField label="Business suggestions" value={strategy.business_suggestions} />

      {strategy.status === "complete" && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex gap-1">
              {PLAN_WINDOWS.map((window) => (
                <Button
                  key={window.days}
                  type="button"
                  size="sm"
                  variant={planDays === window.days ? "default" : "outline"}
                  onClick={() => setPlanDays(window.days)}
                  disabled={generatingPlan}
                >
                  {window.label}
                </Button>
              ))}
            </div>
            <Button onClick={handleGenerateContentPlan} disabled={generatingPlan}>
              {generatingPlan ? "Generating content plan…" : "Generate content plan"}
            </Button>
            <Button
              variant="outline"
              onClick={handleGenerateCollaboration}
              disabled={generatingCollaboration}
            >
              {generatingCollaboration
                ? "Generating collaboration ideas…"
                : "Generate collaboration ideas"}
            </Button>
          </div>
          {planError && <p className="text-sm text-destructive">{planError}</p>}
          {collaborationError && <p className="text-sm text-destructive">{collaborationError}</p>}
        </div>
      )}
    </div>
  );
}

function StrategyField({ label, value }: { label: string; value: string | null }) {
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
