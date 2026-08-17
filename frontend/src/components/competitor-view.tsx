"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import { generateComparison, getCompetitor, type Competitor } from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<Competitor["status"]> = new Set([
  "complete",
  "complete_no_profile",
  "failed",
]);

export function CompetitorView({ initialCompetitor }: { initialCompetitor: Competitor }) {
  const [competitor, setCompetitor] = useState(initialCompetitor);
  const [generatingComparison, setGeneratingComparison] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  // Onboarding runs in the background (scrape + extract takes real
  // wall-clock time, same shape as company onboarding) — poll until terminal.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(competitor.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getCompetitor(competitor.id);
        setCompetitor(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [competitor.id, competitor.status]);

  async function handleGenerateComparison() {
    setGeneratingComparison(true);
    setComparisonError(null);
    try {
      const updated = await generateComparison(competitor.id);
      setCompetitor(updated);
    } catch (err) {
      setComparisonError(describeError(err));
    } finally {
      setGeneratingComparison(false);
    }
  }

  const statusVariant = competitor.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">{competitor.name ?? competitor.url}</h1>
          <a
            href={competitor.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-muted-foreground hover:underline"
          >
            {competitor.url}
          </a>
        </div>
        <Badge variant={statusVariant}>{competitor.status}</Badge>
      </div>

      {competitor.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Onboarding failed{competitor.status_error ? `: ${competitor.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {competitor.status === "complete_no_profile" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              {`We scraped ${competitor.url} successfully, but couldn't generate a profile from it${
                competitor.status_error ? `: ${competitor.status_error}` : "."
              }`}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(competitor.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              Scraping and analyzing this competitor&apos;s website (currently:{" "}
              <code>{competitor.status}</code>).
            </p>
          </CardContent>
        </Card>
      )}

      {competitor.summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed">{competitor.summary}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ProfileField label="Industry" value={competitor.industry} />
        <ProfileField label="Business model" value={competitor.business_model} />
        <ProfileField label="Target audience" value={competitor.target_audience} />
        <ProfileField label="Brand voice" value={competitor.brand_voice} />
        <ProfileField label="Unique value prop" value={competitor.unique_value_prop} full />
      </div>

      {competitor.status === "complete" && competitor.comparison_status === "not_started" && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleGenerateComparison} disabled={generatingComparison}>
              {generatingComparison ? "Generating comparison…" : "Generate comparison"}
            </Button>
          </div>
          {comparisonError && <p className="text-sm text-destructive">{comparisonError}</p>}
        </div>
      )}

      {competitor.comparison_status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Comparison generation failed
              {competitor.comparison_status_error ? `: ${competitor.comparison_status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {competitor.comparison_status === "complete" && (
        <>
          <ComparisonField
            label="Product & pricing comparison"
            value={competitor.product_pricing_comparison}
          />
          <ComparisonField
            label="Marketing strategy analysis"
            value={competitor.marketing_strategy_analysis}
          />
          <ComparisonField label="Competitive gaps" value={competitor.competitive_gaps} />
          <ComparisonField
            label="Strategic recommendations"
            value={competitor.strategic_recommendations}
          />
        </>
      )}
    </div>
  );
}

function ProfileField({
  label,
  value,
  full,
}: {
  label: string;
  value: string | null;
  full?: boolean;
}) {
  return (
    <Card className={full ? "md:col-span-2" : undefined}>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{value ?? <span className="text-muted-foreground">—</span>}</p>
      </CardContent>
    </Card>
  );
}

function ComparisonField({ label, value }: { label: string; value: string | null }) {
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
