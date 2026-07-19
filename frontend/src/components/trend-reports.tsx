"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createTrendReport, listTrendReports, type TrendReport } from "@/lib/api";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function TrendReports({ companyId }: { companyId: string }) {
  const [reports, setReports] = useState<TrendReport[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listTrendReports(companyId)
      .then(({ items }) => setReports(items))
      .catch(() => {});
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      await createTrendReport(companyId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate trend report.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">Trend reports</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {reports.length > 0 && (
          <ul className="flex flex-col gap-2">
            {reports.map((report) => (
              <li key={report.id}>
                <Link
                  href={`/trend-report/${report.id}`}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <span className="truncate text-muted-foreground">
                    {formatDateTime(report.created_at)} · last {report.period_days} days
                  </span>
                  <Badge variant={report.status === "complete" ? "default" : "outline"}>
                    {report.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-3">
          <Button onClick={handleGenerate} disabled={generating}>
            {generating ? "Generating…" : "Generate trend report"}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
