"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getTrendReport, type TrendReport } from "@/lib/api";

const TERMINAL_STATUSES: ReadonlySet<TrendReport["status"]> = new Set(["complete", "failed"]);

export function TrendReportView({ initialReport }: { initialReport: TrendReport }) {
  const [report, setReport] = useState(initialReport);

  // Generation is a synchronous POST, so this row should already be
  // terminal by the time this page renders — poll defensively in case
  // it's ever viewed mid-generation (e.g. a second tab).
  useEffect(() => {
    if (TERMINAL_STATUSES.has(report.status)) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await getTrendReport(report.id);
        setReport(fresh);
        if (TERMINAL_STATUSES.has(fresh.status)) clearInterval(timer);
      } catch {
        // Transient network errors are fine — the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [report.id, report.status]);

  const statusVariant = report.status === "complete" ? "default" : "outline";

  return (
    <div className="mt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Trend report</h1>
        <div className="flex items-center gap-2">
          <Badge variant="outline">last {report.period_days} days</Badge>
          <Badge variant={statusVariant}>{report.status}</Badge>
        </div>
      </div>

      {report.status === "failed" && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">
              Trend report generation failed{report.status_error ? `: ${report.status_error}` : "."}
            </p>
          </CardContent>
        </Card>
      )}

      {!TERMINAL_STATUSES.has(report.status) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Generating trend report…</p>
          </CardContent>
        </Card>
      )}

      <ReportField label="Summary" value={report.summary} />

      {report.key_themes && report.key_themes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Key themes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {report.key_themes.map((theme) => (
                <Badge key={theme} variant="outline">
                  {theme}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <ReportField label="Notable trends" value={report.notable_trends_summary} />
      <ReportField label="Content opportunities" value={report.content_opportunities} />
      <ReportField label="Campaign alignment" value={report.campaign_alignment_notes} />
      <ReportField label="Competitor relevance" value={report.competitor_relevance_notes} />
    </div>
  );
}

function ReportField({ label, value }: { label: string; value: string | null }) {
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
