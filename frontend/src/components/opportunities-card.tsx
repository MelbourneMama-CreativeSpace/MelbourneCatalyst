"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { describeError } from "@/lib/api-error";
import { generateContentOpportunities, type Opportunity } from "@/lib/api";

const PRIORITY_BADGE_STYLES: Record<Opportunity["priority"], string> = {
  high: "bg-primary/15 text-primary",
  medium: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  low: "",
};

export function OpportunitiesCard({ companyId }: { companyId: string }) {
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const res = await generateContentOpportunities(companyId);
      setOpportunities(res.items);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Content opportunities</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Grounded in this company&apos;s own relevant trends, upcoming seasonal dates, and (once
          any exists) its own real performance data.
        </p>

        {opportunities && opportunities.length > 0 && (
          <ul className="flex flex-col gap-2">
            {opportunities.map((o, i) => (
              <li key={i} className="rounded-md border border-border p-3 text-sm">
                <div className="mb-1 flex items-center gap-2">
                  <Badge className={PRIORITY_BADGE_STYLES[o.priority]} variant="default">
                    {o.priority}
                  </Badge>
                  <Badge variant="outline" className="capitalize">
                    {o.source}
                  </Badge>
                </div>
                <p className="font-medium">{o.title}</p>
                <p className="mt-0.5 text-muted-foreground">{o.reasoning}</p>
              </li>
            ))}
          </ul>
        )}
        {opportunities !== null && opportunities.length === 0 && (
          <p className="text-sm text-muted-foreground">No opportunities surfaced this time.</p>
        )}

        <div>
          <Button onClick={handleGenerate} disabled={generating}>
            {generating ? "Finding opportunities…" : opportunities ? "Refresh" : "Find opportunities"}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
